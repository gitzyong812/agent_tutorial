[中文](./README.md) | [English](./README-en.md)

[← Previous Chapter](../chapter5_harness/README-en.md) | [Back to Contents](../README-en.md) | [Next Chapter →](../chapter7_opc_applications/README-en.md)

> Supporting code: [open the code directory](./code/)

# Multi-Agent Collaboration Systems

The first five chapters developed a single digital employee by adding conversation, knowledge, tools, memory, and Harness engineering. As the scope grows, one agent may have to understand requirements, retrieve material, perform actions, and inspect the result. Concentrating too many responsibilities in one agent produces longer prompts, broader permissions, and harder diagnosis. This chapter organizes agents with clear responsibilities into a collaborative system and examines team construction, task flow, result aggregation, and safe termination.

A multi-agent system is more than several model calls. Collaboration is worthwhile only when clear role separation reduces complexity or when different steps genuinely need different knowledge, tools, contexts, or permissions. A single agent or deterministic workflow is usually cheaper and more reliable for a simple, bounded task. This chapter therefore separates two related design questions: how the team is organized and how context, control flow, and results are managed at runtime.

After completing this chapter, you should be able to:

1. Explain the appropriate boundaries of single-agent and multi-agent systems.
1. Define roles, responsibilities, inputs, outputs, and tool permissions.
1. Compare supervisor and peer-to-peer organizational topologies.
1. Select a task-execution topology from task dependencies.
1. Design team context, handoff, aggregation, and review mechanisms.
1. Add basic runtime safeguards to a multi-agent system.

## Building a Multi-Agent Team

### From One Agent to a Team

A single agent suits a clear goal with few steps and a limited tool set. A customer-service agent, for example, can retrieve a manual and answer common questions. If it must also analyze needs, generate a proposal, verify prices, review compliance, and send the result, a single prompt is likely to suffer from conflicting responsibilities, excessive context, and excessive authority.

[Figure 6-1](#fig-single-to-multi-agent) divides such work among agents with distinct prompts, contexts, and tools. A requirements agent extracts constraints, a proposal agent generates candidates, a reviewer checks facts and rules, and a coordinator plans and aggregates. The agents may use the same model or different models. What makes the system multi-agent is the presence of relatively independent roles, states, and collaboration relationships.

<a id="fig-single-to-multi-agent"></a>

![Separating responsibilities from one agent into a multi-agent team](./imgs/single-to-multi-agent.png)

*Figure 6-1. Separating responsibilities from one agent into a multi-agent team*

Consider four questions before using multiple agents:

1. Can the task be divided into reasonably clear subtasks?
1. Do those subtasks need different knowledge, tools, contexts, or permissions?
1. Can roles work in parallel or gain new verification evidence from external tools?
1. Is the gain in quality, speed, or control worth the extra model calls and coordination?

If the answers are unclear, begin with one agent. Under an equal reasoning budget, multi-agent systems do not necessarily outperform a single agent on multi-step reasoning, and message passing may lose information<sup>[1](#ref-tran2026singleagent)</sup>. The useful comparison is therefore performance on the same task, under a similar budget and acceptance standard. Anthropic likewise reports that multi-agent research is most useful for high-value tasks with parallel search, large information volumes, and diverse tools, while consuming substantially more tokens than ordinary conversation<sup>[2](#ref-anthropic2025multiagent)</sup>.

<a id="tab-single-vs-multi-agent"></a>

*Table 6-1. Guidance for choosing a single agent or multiple agents*

| Dimension | Prefer a single agent | Consider multiple agents |
| --- | --- | --- |
| Task structure | Few steps with a clear goal and path | Several specialist subtasks or complex dependencies |
| Context | One context holds the required information | Roles need separate contexts or the total material is too large |
| Tools and permissions | Few tools with similar permissions | Steps require substantially different tools and permissions |
| Execution | Work follows one continuous path | Subtasks can run in parallel or need independent viewpoints |
| Verification | Relies mainly on model judgment | Can use retrieval, tests, calculation, or human feedback |
| Cost and value | Low-value task emphasizing latency and cost | Quality gains can justify coordination cost |

### Designing Roles and Responsibilities

Role design creates clear accountability rather than imitating job titles. An executable role definition should include:

- **Goal:** what the agent is and is not responsible for.
- **Input:** facts, constraints, and upstream artifacts it receives.
- **Output:** required fields, format, and quality criteria.
- **Tools:** data it may read and actions it may perform.
- **Context:** team information it can see and work records that remain private.
- **Stopping conditions:** when to finish, retry, hand off, or request a person.

Minimize overlap. Splitting is rarely useful when two agents receive the same input, use the same tools, and produce the same result. It is more valuable when a reviewer can obtain new evidence with tests or retrieval that was unavailable during generation.

A coordinator should retain the overall goal, plan, state, and artifact index rather than every source document. Specialists receive only the material required for their current subtask and return structured results. This controls context length and makes roles easier to test and replace.

### Organizational Topologies

Organizational topology describes how control and information move among agents. [Figure 6-2](#fig-organization-topology) presents supervisor and peer-to-peer topologies. They answer who coordinates, while the later execution topologies answer how work unfolds.

<a id="fig-organization-topology"></a>

![Two basic organizational topologies](./imgs/organization-topology.png)

*Figure 6-2. Two basic organizational topologies*

**Supervisor topology.** A coordinator understands the overall goal, decomposes work, selects roles, tracks state, and aggregates results. Accountability, budgets, and stopping conditions are clear, making it suitable for business processes with a defined deliverable. The coordinator can become a bottleneck or send every role in the wrong direction after a bad decomposition.

**Peer-to-peer topology.** Agents have similar standing and may request help, challenge a result, or hand off control directly. It is flexible for discussion and dynamic routing among a few specialists, but it creates more complex message relationships and increases duplicate work, unclear ownership, and handoff loops. A teaching project should master the supervisor pattern first.

<a id="tab-organization-topology"></a>

*Table 6-2. Supervisor and peer-to-peer organizational topologies*

| Item | Supervisor | Peer-to-peer |
| --- | --- | --- |
| Control | Coordinator plans and schedules | Control moves with task handoffs |
| Main advantage | Clear state, limits, tracking, and aggregation | Flexible direct negotiation and handoff |
| Main risk | Coordinator bottleneck or single point of failure | Complex messages, loops, or unclear ownership |
| Suitable tasks | Complex work with a clear owner and delivery process | Dynamic routing and iteration among a few specialists |

## Running Multi-Agent Collaboration

### Multi-Agent Context Management

Team context combines shared team state, private agent state, and long-term team memory. These mechanisms respectively support current collaboration, role focus, and learning across tasks.

<a id="fig-team-context-memory"></a>

![Shared, isolated, and long-term memory in a multi-agent team](./imgs/team-context-memory.png)

*Figure 6-3. Shared, isolated, and long-term memory in a multi-agent team*

#### Team Sharing

A shared workspace stores the task goal, confirmed facts, status, and public artifacts. A planner publishes subtasks, executors write results, and reviewers record requested changes. A task-state table, shared files, and a message bus can implement the workspace. A teaching project may start with a Python dictionary and a local artifact directory.

Sharing does not mean publishing every execution trace. Only collaboration-relevant information should be shared so that prompts, failed attempts, and irrelevant tool output do not inflate every context.

#### Agent Isolation

Each agent retains a private role prompt, local task trace, and specialist tool results. Isolation shortens context, reduces distraction, supports parallel work, and enables permission control. A handoff should exchange the goal, necessary input, constraints, acceptance criteria, and artifact location so that the receiver does not need the sender's full trace.

#### Evolving Long-Term Team Memory

The shared workspace serves the current task. Long-term team or organizational memory stores facts and experience that remain useful across tasks. Facts include business rules, project constraints, and confirmed conclusions. Experience includes effective processes, failure causes, and collaboration methods.

The system extracts durable information from a completed task, organizes it into team memory, and retrieves it for later work. It should not retain every history item. Each memory needs a source, time, scope, and mechanisms for merging, updating, and removal. Unverified judgments must not become team facts, and access to sensitive information must remain restricted.

### Task-Execution Topologies

Organizational topology determines control; task topology determines how one job uses several agents. Following a research classification under equal reasoning budgets, this section presents sequential execution, parallel subtasks, parallel roles, debate, and ensemble execution<sup>[1](#ref-tran2026singleagent)</sup>.

<a id="fig-five-task-topologies"></a>

![Five task-execution topologies](./imgs/five-task-topologies.png)

*Figure 6-4. Five task-execution topologies*

**Sequential execution** passes the output of one dependent step to the next and finally aggregates all intermediate results. It suits a pipeline such as requirements, retrieval, proposal, and review. Every step needs a clear artifact so that downstream roles do not guess vague conclusions.

**Parallel subtasks** divide work into nearly independent components that execute concurrently before aggregation. Product research might separately cover customer needs, competitors, cost, and regulation. Forced parallelism between dependent steps only creates rework.

**Parallel roles** give the full problem to specialists with different viewpoints. One role proposes a solution, another extracts facts and constraints, a critic searches for flaws, and another independently solves the task. This differs from parallel subtasks: one divides the problem by component, the other by perspective.

**Debate** lets two roles answer independently, criticize each other's work, and pass answers and criticism to an aggregator. It can expose assumptions, but intensity is not factual verification. The method is more useful when roles have different evidence, tools, or explicit evaluation dimensions.

**Ensemble execution** generates independent candidates, possibly with more sampling variation, and lets a judge select against common criteria. It suits objectively checkable tasks such as tests, rule compliance, or quantitative scores. Vague judging criteria make more candidates only more expensive.

No topology is universally best. First identify the desired increment: lower latency, broader evidence, risk discovery, or more candidates. Add agents only when that increment justifies the cost.

### Dynamic Task Planning and Execution

Fixed topologies suit stable tasks. For complex work whose steps and dependencies are unknown in advance, a supervisor can inspect team responsibilities and dynamically build an execution graph. The process has planning and graph-execution stages.

<a id="fig-dynamic-task-dag"></a>

![Dynamic task planning and dependency-graph execution](./imgs/dynamic-task-dag.png)

*Figure 6-5. Dynamic task planning and dependency-graph execution*

#### Task Planning

Starting from the user goal, the supervisor reads team responsibilities, recent conversation, team memory, and shared files. It produces bounded subtasks with an identifier, executor, content, and dependencies. A simplified planning prompt is:

```text
你是多智能体团队的任务规划器。

请根据用户目标和团队成员职责完成以下工作：
1. 将复杂任务拆成边界明确的子任务；
2. 为每个子任务选择一名合适的执行角色；
3. 使用 depends_on 标明前置任务；
4. 没有依赖的任务将 depends_on 设为空数组；
5. 依赖只能引用前面已经定义的任务。

只返回 JSON：
\{
  "tasks": [
    \{
      "agent_id": 1,
      "content": "任务内容",
      "depends_on": ["task-1"]
    \}
  ]
\}
```

The system assigns `task-1`, `task-2`, and later identifiers in response order. `depends_on` links them into a directed acyclic graph. Nodes without prerequisites can run together. For example, product-term retrieval and customer analysis run in parallel, a recommendation depends on both, and a customer response depends on the recommendation. Before execution, validate agents, dependency identifiers, acyclicity, task count, and total budget.

#### Executing the Dependency Graph

The executor first runs all nodes without unmet dependencies in one parallel batch. It stores their results and then identifies the next ready batch. A downstream role receives its own task and only the necessary upstream results.

The process repeats until every node completes and the aggregator receives the results. If unfinished nodes remain but none is ready, the graph contains a cycle or unknown dependency and execution must stop with an error.

### Aggregation, Review, and Revision

An aggregator merges information, removes duplication, resolves conflicts, and preserves evidence. A judge selects among candidates using common criteria. Neither may invent unsupported facts.

A reviewer checks facts, format, and business rules against a checklist. A failed review states the problem, evidence, and required change, after which the original executor revises. Prefer external feedback such as tests, recalculation, authoritative retrieval, or rendered output, and limit revision rounds before handing off to a person.

## Safeguarding Multi-Agent Systems

With several roles, tool calls, and handoffs, a fault at any point may affect the final result. The system needs stable termination, permission boundaries, and human decisions for high-risk work.

<a id="fig-multi-agent-safeguards"></a>

![Basic safeguards for a multi-agent system](./imgs/multi-agent-safeguards.png)

*Figure 6-6. Basic safeguards for a multi-agent system*

### Timeouts, Retries, and Stopping Conditions

Track each subtask as pending, running, completed, failed, cancelled, or waiting for a person. The coordinator uses these states to continue, retry, or stop without indefinite waits and handoff loops.

Set a per-call timeout, limited retries for recoverable errors, and global limits on rounds and budget. Retries should include the failure reason rather than repeat unchanged work. Stop normally when the goal is reached or the user cancels. Stop automation and hand off when the budget is exhausted, the same error repeats, or critical information is missing. Task identifiers and idempotency checks prevent retrying a write twice.

### Permission Isolation and Human Review

Give every role the minimum tools and data its responsibility requires. An analyst may read sources; an executor may draft an operation request but should not perform a high-risk write directly. Role separation is not security unless the program enforces the permissions.

Apply least visibility to shared state. Public goals, status, and non-sensitive artifacts may be visible to the team. Personal information, secrets, and privileged tool results should be available only to necessary roles. Use versioning or locks when several agents modify the same data.

External publication, customer commitments, financial operations, private-data processing, and irreversible actions require human review. The reviewer sees the goal, key input, evidence, proposed action, and risk, then approves, rejects, or requests revision. Record the decision and use it to continue or terminate.

<a id="tab-multi-agent-safeguards"></a>

*Table 6-3. Common multi-agent risks and safeguards*

| Risk | Typical symptom | Safeguard |
| --- | --- | --- |
| Non-termination | Roles repeatedly hand off or revise | Maximum rounds, total budget, human exit |
| Cascading errors | Downstream roles reuse a bad result | Evidence records, stage validation |
| Conflicting parallel results | Roles reach contradictory conclusions | Conflict checks, unified aggregation |
| Duplicate execution | A retry sends or writes twice | Task identifiers, idempotency checks |
| Excess authority | A role accesses unauthorized data or tools | Least privilege, human review |

## Hands-On Practice: Build a Multi-Agent Team

This practice extends the system from the first five chapters and uses real digital employees rather than ordinary functions. You will create a web-based team and observe shared context, role isolation, dynamic planning, and dependency-graph execution. The scenario is a publicity plan for a “Campus AI Innovation Week.” The team verifies event facts, analyzes channels, writes copy, and performs a pre-publication review.

Fact checking and channel analysis can run in parallel, copywriting depends on both, and final review depends on the copy.

<a id="tab-multi-agent-practice-map"></a>

*Table 6-4. Practice flow and code modules*

| Area | Question | Main code |
| --- | --- | --- |
| Team construction | How do members acquire clear boundaries? | `models.py`, `group_chat/service.py` |
| Context management | What is shared and what remains isolated? | `group_chat/environment.py` |
| Planning | How does a goal become a dependency graph? | `group_chat/tasks.py` |
| Execution | How do ready tasks run in parallel and pass results? | `group_chat/executor.py` |
| Safety | How are high-risk effects and unrecoverable pauses avoided? | `runners/react.py` |

### Step 1: Prepare the System and Models

```bash
cd {本章项目代码目录}
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. The local SQLite database adds tables for team conversations, members, shared messages, memories, and files while retaining all earlier features.

Configure and test an OpenAI-compatible model. ChatBot and RAG team members use their bound models, while the dynamic planner has a separate configuration:

```text
GROUP_TASK_PLANNER_MODE=llm
GROUP_TASK_PLANNER_BASE_URL={模型服务地址}
GROUP_TASK_PLANNER_MODEL_NAME={模型名称}
GROUP_TASK_PLANNER_API_KEY={模型密钥}
GROUP_TASK_PLANNER_MAX_TOKENS=1024
```

Restart after changing the configuration. If the planner is absent, fails, or returns invalid output, the system falls back to rule-based planning. The fallback understands `@数字员工名` and dependency phrases such as “根据上面结果” but not complex role relationships.

### Step 2: Create Specialist Roles and a Team

Create and publish four digital employees with distinct instructions and output requirements.

<a id="tab-multi-agent-practice-roles"></a>

*Table 6-5. Roles for the campus-event publicity team*

| Role | Responsibility | Output requirement |
| --- | --- | --- |
| Fact checker | Extract time, place, audience, and constraints | Confirmed facts and unresolved items; no publicity copy |
| Channel analyst | Analyze official accounts, groups, and campus posters | Channels, target audiences, and release suggestions |
| Copywriter | Create a plan from confirmed facts and channel advice | Title, body, and channel variants without unknown facts |
| Content reviewer | Check facts, wording, format, and publication risks | Approve or return with specific revision requests |

On Team Collaboration, create “Campus AI Innovation Week Publicity Team” with the four published agents. Members cannot be duplicated. The page shows team conversations on the left, the shared message stream in the center, and members, shared memory, and files on the right.

<a id="fig-multi-agent-practice-team-setup"></a>

![Creating a publicity team with four specialist roles](./imgs/chapter6_practice_team_setup.png)

*Figure 6-7. Creating a publicity team with four specialist roles*

### Step 3: Prepare Shared Team Context

Team creation adds a `workspace` memory automatically. Add an event rule and a shared text file, replacing the team ID with the actual value.

```bash
curl -X POST http://127.0.0.1:8000/api/group-conversations/1/memories \
  -H "Content-Type: application/json" \
  -d '{"key":"发布规则","content":"未经确认的信息不得写入正式文案"}'

curl -X POST http://127.0.0.1:8000/api/group-conversations/1/files \
  -H "Content-Type: application/json" \
  -d '{"filename":"activity-brief.md","content":"活动名称：校园人工智能创新周\n时间：11月18日至22日\n地点：大学生活动中心\n对象：全校师生\n待核实：报名截止时间","content_type":"text/markdown"}'
```

After refresh, every member can read the shared memory and file but not another member's full local tool trace. `environment_prompt` builds the shared environment, and `with_group_context` combines it with the current role prompt. Edit the file to contain a wrong date and observe how a shared error affects both fact checking and review. Shared state reduces repeated transmission but can amplify bad facts.

### Step 4: Generate a Task Dependency Graph

Submit the following goal without assigning members with `@`:

```text
请为校园人工智能创新周制定宣传方案。
先核对共享文件中的活动事实，并分析适合的传播渠道；
再根据已确认事实和渠道建议撰写宣传文案；
最后检查事实、措辞和发布风险，给出通过或退回结论。
报名截止时间尚未确认，不得自行补写。
```

The planner reads the goal, roles, recent messages, shared memory, and files. Ideally, fact checking and channel analysis have no dependencies, copywriting depends on both, and review depends on copywriting. Invalid agents, forward references, or malformed JSON invalidate the model plan and trigger the rule fallback.

```text
task-1 事实核查员：核对活动资料           depends_on=[]
task-2 渠道分析员：提出传播渠道建议       depends_on=[]
task-3 宣传文案员：生成宣传方案           depends_on=[task-1, task-2]
task-4 内容审核员：审核宣传方案           depends_on=[task-3]
```

The system assigns IDs in response order. If planning is empty or invalid, it does not execute an untrusted graph and instead creates an executable rule-based plan.

### Step 5: Observe Graph Execution and Result Passing

The executor groups every currently ready node into the same parallel batch. The expected batches are[^1]:

```text
[task-1, task-2] -> [task-3] -> [task-4]
```

Each batch uses at most six workers. Downstream roles receive their task, shared context, and necessary upstream results, not unrelated local traces. The page gives every task a separate streaming area for its answer, sources, and ReAct trace.

<a id="fig-multi-agent-practice-execution"></a>

![Multi-role results and review after executing the dependency graph](./imgs/chapter6_practice_execution.png)

*Figure 6-8. Multi-role results and review after executing the dependency graph*

Use `curl -N` to inspect task IDs and dependencies. In named SSE events, `agent_start` contains the ID, role, task, and `depends_on`; `delta` carries answer fragments; `agent_done` completes a node; and `done` completes the collaboration.

```bash
curl -N -X POST http://127.0.0.1:8000/api/group-conversations/1/messages \
  -H "Content-Type: application/json" \
  -d '{"content":"请核对事实并形成宣传方案，最后完成审核"}'
```

### Step 6: Verify Explicit Assignment, Fallback, and Safety Limits

1. **Explicit assignment:** enter “`@事实核查员 请列出已确认事实`” to call only that member. Multiple `@` sections create corresponding tasks.
1. **Rule fallback:** set `GROUP_TASK_PLANNER_MODE` to `keyword`, restart, and send an assigned task. Verify role assignment and sequential dependencies from phrases such as “根据上面结果”.
1. **Permission limits:** add a ReActAgent to the team. Team execution withholds write tools, `ask_human`, and Skill creation. It retains read-only tools, knowledge and memory retrieval, and structured handoff instructions. This prevents parallel nodes from waiting on web-only approvals or performing high-risk operations without recoverable state.

Run the chapter tests:

```bash
python -m pytest -q tests/test_group_chat.py
```

They cover explicit assignment, planning without an assigned member, dependency batches, rejection of unknown dependencies, upstream result passing, shared context, team APIs, SSE persistence, and ReActAgent permission limits.

### Practice Tasks and Checklist

1. Create four agents with distinct responsibilities, inputs, outputs, and exclusions.
1. Create a team, add one shared rule and one text file, and verify that all members read the same content.
1. Generate a task graph with at least one parallel batch and one downstream dependency. Record IDs, roles, and `depends_on`.
1. Check that fact verification, channel advice, copywriting, and review each add useful information.
1. Run one explicitly assigned `@` task and verify that the system does not invent a registration deadline.

### Expected Outcomes

Submit the team role configuration, shared-context explanation, dependency graph, normal run, one fallback run, and one safety-limit check. Include screenshots of the workspace and complete collaboration while hiding model keys and other sensitive information.

Explain why fact checking and channel analysis can run in parallel, why the copywriter should receive only necessary upstream results, and why a team ReActAgent does not expose write tools or pause-for-human behavior directly. The value of the system should come from clear division, useful information exchange, and verifiable execution rather than more model calls.

## Exercises and Discussion

1. Design a multi-agent team for sales, customer service, or software development and justify using it instead of one agent.
1. Explain the difference between organizational and task-execution topologies, and give a suitable scenario for supervisor and peer-to-peer teams.
1. Use the code to explain how shared workspace, private agent context, and long-term team memory coexist.
1. Draw a task graph with at least four nodes and label parallel batches, dependencies, and aggregation.
1. Explain validation, fallback, and termination when the planner emits an unknown role, invalid dependency, or cycle.
1. Design least-privilege and human-review rules for team tools, distinguishing automatic actions from human-only actions.

## References

1. <a id="ref-tran2026singleagent"></a>Dat Tran, Douwe Kiela. Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets. 2026. [DOI](https://doi.org/10.48550/arXiv.2604.02460).

2. <a id="ref-anthropic2025multiagent"></a>Anthropic. [How We Built Our Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system).

[^1]: This is the ideal plan. Model intent understanding and randomness may produce a different plan, so you can refine the prompt and try again.

---

[← Previous Chapter](../chapter5_harness/README-en.md) | [Back to Contents](../README-en.md) | [Next Chapter →](../chapter7_opc_applications/README-en.md)
