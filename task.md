Intern Problem Statement
Autonomous AI Task Worker
Companies perform many repetitive tasks that involve reading information, deciding what to do next, using websites or applications, and checking whether the task was completed correctly.
Today, a person often has to manually move between different tools to complete even a simple request.
Build a prototype of an AI worker that can take a natural language task and autonomously attempt to complete it using a computer.
For example, a user might say:
“Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done.”
The system should ideally be capable of:
Understanding the user’s end goal rather than requiring every step to be specified.
Breaking the request into a sequence of actions.
Using available tools such as a browser, files, APIs, or a simulated company application.
Observing the result of each action.
Deciding what to do next based on what happened.
Remembering relevant information discovered during execution.
Detecting when an action fails.
Attempting a reasonable alternative or retry where appropriate.
Verifying whether the requested outcome was actually achieved.
Asking the user for clarification or approval when it cannot safely proceed.
Returning a concise summary and useful evidence of completion.
Scope
You do not need to build a production ready system.
You do not need to support every website, desktop application, or business workflow.
You may restrict your prototype to a small environment, simulated company application, browser environment, or limited set of tools.
A narrow prototype that genuinely works is better than a broad system where most functionality is mocked.
We are intentionally not prescribing the architecture, model, framework, interface, or exact workflow.
We want to see how you interpret the problem and what you believe a useful autonomous AI worker should look like.
Evaluation Criteria
For both roles, submissions will primarily be evaluated on:
Autonomy — Can the system determine and execute meaningful next actions without being told every individual step?
Execution — Does the system actually perform work rather than merely explain what should be done?
Reliability — How does it handle unexpected states, errors, retries, and failures?
Verification — Does it determine whether the requested outcome was actually achieved?
Generalization — How much of the system can remain unchanged when given a different task?
Engineering Quality — Architecture, implementation, code quality, debugging, and technical judgment.
Product Thinking — Does the solution focus on accomplishing the user’s actual objective?
Technical Understanding — Can you clearly explain why you built the system the way you did?
We are not evaluating submissions based simply on the number of features implemented.
Submission Requirements
Please submit:
GitHub repository or equivalent source-code link.
README containing setup and run instructions.
Short explanation of the architecture.
Explanation of important technical/design decisions.
Demo video or accessible live demo showing the prototype working.
Known limitations.
What you would build next if given additional time.
Any assumptions made while building the solution.
Details of models, APIs, frameworks, external services, or pre-built components used.
You may use AI coding tools such as Claude, Cursor, ChatGPT, Copilot, or similar tools.
Using AI tools is not a disadvantage.
We care about the quality of what you build and whether you understand the system you submit.
Be prepared to explain, debug, or modify your implementation during the technical discussion.
Do not use real company credentials, confidential information, or unauthorized access to third party systems. Use sandbox/mock environments wherever appropriate.

