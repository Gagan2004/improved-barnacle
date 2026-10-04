from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from worker.loop import AgentLoop, RunState


class RunManager:
    def __init__(self) -> None:
        self.runs: dict[str, RunState] = {}
        self.queues: dict[str, asyncio.Queue] = {}
        self.replies: dict[str, asyncio.Future] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    def get(self, run_id: str) -> RunState | None:
        return self.runs.get(run_id)

    async def emit(self, run_id: str, event: dict[str, Any]) -> None:
        queue = self.queues.get(run_id)
        if queue:
            await queue.put(event)

    async def wait_user(self, run_id: str, question: str) -> str:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self.replies[run_id] = future
        return await future

    def answer(self, run_id: str, text: str) -> None:
        future = self.replies.get(run_id)
        if future and not future.done():
            future.set_result(text)

    def start(self, goal: str) -> RunState:
        run_id = uuid4().hex[:10]
        state = RunState(id=run_id, goal=goal)
        self.runs[run_id] = state
        self.queues[run_id] = asyncio.Queue()

        async def emit(event: dict[str, Any]) -> None:
            await self.emit(run_id, event)

        async def wait_user(question: str) -> str:
            return await self.wait_user(run_id, question)

        agent = AgentLoop(state, emit, wait_user)
        self.tasks[run_id] = asyncio.create_task(self._guard(agent))
        return state

    async def _guard(self, agent: AgentLoop) -> None:
        try:
            await agent.run()
        except Exception as exc:
            agent.state.status = "failed"
            agent.state.error = str(exc)
            await agent._observe("error", {"error": str(exc)})
            agent._persist()
        finally:
            queue = self.queues.get(agent.state.id)
            if queue:
                await queue.put({"kind": "end", "payload": {}})


MANAGER = RunManager()
