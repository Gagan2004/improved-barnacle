from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from apps.config import DOWNLOAD_DIR, WORKER_BASE_URL, ensure_dirs

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


def assert_local_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http(s) URLs are allowed")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"Blocked non-localhost URL: {url}")
    return url


class BrowserSession:
    def __init__(self, run_dir: Path, base_url: str = WORKER_BASE_URL):
        self.run_dir = run_dir
        self.base_url = base_url.rstrip("/")
        self._pw = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.shot_index = 0
        self.last_download: Path | None = None

    async def start(self) -> None:
        ensure_dirs()
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(headless=True)
        self.context = await self.browser.new_context(accept_downloads=True)
        self.page = await self.context.new_page()

    async def close(self) -> None:
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()

    def _page(self) -> Page:
        if not self.page:
            raise RuntimeError("Browser not started")
        return self.page

    def resolve(self, url: str) -> str:
        if url.startswith("/"):
            url = self.base_url + url
        return assert_local_url(url)

    async def screenshot(self) -> str | None:
        page = self._page()
        self.shot_index += 1
        path = self.run_dir / f"shot_{self.shot_index:03d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path), full_page=True)
        return str(path)

    async def snapshot(self, with_shot: bool = True) -> dict[str, Any]:
        page = self._page()
        controls = []
        locators = page.locator("a, button, input, select, textarea, [id]")
        count = min(await locators.count(), 80)
        for i in range(count):
            el = locators.nth(i)
            tag = await el.evaluate("e => e.tagName.toLowerCase()")
            el_id = await el.get_attribute("id")
            name = await el.get_attribute("name")
            href = await el.get_attribute("href")
            typ = await el.get_attribute("type")
            text = (await el.inner_text()).strip()[:80] if tag in {"a", "button", "label"} else ""
            placeholder = await el.get_attribute("placeholder")
            selector = None
            if el_id:
                selector = f"#{el_id}"
            elif name:
                selector = f"[name='{name}']"
            controls.append(
                {
                    "tag": tag,
                    "id": el_id,
                    "name": name,
                    "type": typ,
                    "href": href,
                    "text": text,
                    "placeholder": placeholder,
                    "selector": selector,
                }
            )
        body = await page.inner_text("body")
        shot = await self.screenshot() if with_shot else None
        return {
            "url": page.url,
            "title": await page.title(),
            "text": body[:6000],
            "controls": controls,
            "screenshot": shot,
            "last_download": str(self.last_download) if self.last_download else None,
        }

    async def goto(self, url: str) -> dict[str, Any]:
        page = self._page()
        target = self.resolve(url)
        await page.goto(target, wait_until="domcontentloaded")
        return await self.snapshot()

    async def click(self, selector: str) -> dict[str, Any]:
        page = self._page()
        downloaded: list = []

        def on_download(download) -> None:
            downloaded.append(download)

        page.once("download", on_download)
        await page.locator(selector).first.click(timeout=8000)
        if downloaded:
            download = downloaded[0]
            dest = DOWNLOAD_DIR / download.suggested_filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            await download.save_as(str(dest))
            self.last_download = dest
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=4000)
        except Exception:
            pass
        return await self.snapshot()

    async def type_text(self, selector: str, text: str, submit: bool = False) -> dict[str, Any]:
        page = self._page()
        loc = page.locator(selector).first
        await loc.fill(text)
        if submit:
            await loc.press("Enter")
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
        return await self.snapshot()

    async def read(self) -> dict[str, Any]:
        return await self.snapshot()

    async def save_download_from_href(self, url: str) -> dict[str, Any]:
        page = self._page()
        target = self.resolve(url)
        dest_dir = DOWNLOAD_DIR
        dest_dir.mkdir(parents=True, exist_ok=True)
        async with page.expect_download() as download_info:
            await page.goto(target)
        download = await download_info.value
        dest = dest_dir / download.suggested_filename
        await download.save_as(str(dest))
        self.last_download = dest
        return {"saved": str(dest), "url": target}
