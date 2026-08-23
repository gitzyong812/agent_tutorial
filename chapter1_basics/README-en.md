[中文](./README.md) | [English](./README-en.md)

[Back to Contents](../README-en.md) | [Next Chapter →](../chapter2_chatbot/README-en.md)

> Companion code for this chapter: [open the code directory](./code/README-en.md)

# Foundations of Large Language Models and Agents

In this chapter, we will study the foundations of artificial intelligence, large language models, and agents, and make our first large language model API call.
After completing the chapter, you should be able to explain the relationship among AI, large language models, and agents, configure a development environment, and run a minimal working example.
To avoid becoming immersed in tools and code too early, we begin with the basic idea of an agent, explain why large language models change how agents are built, and finally turn these concepts into a runnable minimal Python project.

## Foundations of Artificial Intelligence

### Artificial Intelligence and Agents

What is artificial intelligence (AI)? An intuitive interpretation is to enable a machine to act like a capable assistant, choosing appropriate actions according to its goal and environment. AI has received many definitions throughout its history. As shown in Table [1-1](#tab-ai-definition-perspectives), some definitions ask whether a machine can think or act like a human. Others are less concerned with imitation and ask whether a machine can complete tasks rationally.
This tutorial adopts an interpretation better suited to engineering practice. If a system can perceive its environment, make judgments according to a goal, and take reasonably appropriate actions, we can regard it as an artificial intelligence system<sup>[1](#ref-russell2020aima)</sup>. Such a system is commonly called an agent.

From this perspective, a central goal of AI is to build agents capable of completing tasks. An agent need not be identical to a human or truly conscious. What matters is whether it can pursue a goal, observe the current situation, choose appropriate methods, and complete the task step by step. The history of AI can therefore also be understood as a history of building increasingly capable agents.
The following table presents several representative views of artificial intelligence. You do not need to memorize every definition. Its purpose is to explain why this tutorial emphasizes rational action: the digital employees we will build are software agents that continuously act toward business goals.

<a id="tab-ai-definition-perspectives"></a>

*Table 1-1. Four representative perspectives on artificial intelligence<sup>[1](#ref-russell2020aima)</sup>*

| **Thinking humanly** | **Thinking rationally** |
| --- | --- |
| “The exciting new effort to make computers think ... machines with minds, in the full and literal sense” (Haugeland, 1985)<br><br>“The automation of activities that we associate with human thinking, activities such as decision-making, problem solving, learning...” (Bellman, 1978) | “The study of mental faculties through the use of computational models” (Charniak and McDermott, 1985)<br><br>“The study of the computations that make it possible to perceive, reason, and act” (Winston, 1992) |
| **Acting humanly** | **Acting rationally (the perspective used in this tutorial)** |
| “The art of creating machines that perform functions that require intelligence when performed by people” (Kurzweil, 1990)<br><br>“The study of how to make computers do things at which, at the moment, people are better” (Rich and Knight, 1991) | “Computational intelligence is the study of the design of intelligent agents” (Poole et al., 1998)<br><br>“AI ... is concerned with intelligent behavior in artifacts” (Nilsson, 1998) |

The development of agents can be summarized as a progression from hand-written rules, to learning algorithms, and then to general task-execution frameworks driven by large language models. Early AI primarily relied on symbolic representations and rule-based reasoning. Researchers represented human knowledge as logical rules, search spaces, or conditions in expert systems, then had machines use these rules for reasoning, planning, and decision-making. In board games and expert diagnostic systems, for example, an agent's core capability came from a clearly defined problem space, an enumerable set of actions, and manually designed reasoning rules.
Research gradually shifted from writing complete rules to enabling systems to learn and adapt within an environment. Reactive agents emphasize acting quickly on current perceptions. Reinforcement-learning agents learn policies that connect states, actions, and rewards through trial and error. Fields such as robotics and autonomous driving further require agents to handle perception, control, planning, and safety constraints together.
In recent years, large language models have created new possibilities for agent development. A model can understand language, integrate knowledge, generate code, and decompose tasks, allowing it to serve to some extent as an agent's decision-making brain. Once connected to tools, memory, knowledge bases, and external systems, an agent does more than answer questions. It can plan toward a goal, call tools, observe results, and continually adjust its actions.
Understanding today's LLM agents therefore requires more than checking whether a model can chat. We must return to the basic structure of an agent and understand how it perceives the environment, makes decisions, and acts.

### Traditional Agent Development Is Complex Systems Engineering

An agent is not an isolated program. It must interact with an environment to achieve its goal. The environment may be a simple rule system, such as a board game, web form, or enterprise application, or a complex physical world, such as a robot's room or a production line. In either case, an agent usually needs perception, planning, decision-making, and action modules. Each module draws on different disciplines, making traditional agent development a complex engineering effort.

<a id="fig-trad-agent"></a>

![Structure of a traditional artificial agent](./imgs/trad_agent.png)

*Figure 1-1. Structure of a traditional artificial agent*

As Figure [1-1](#fig-trad-agent) shows, a traditional agent is essentially a perception–decision–action–feedback loop. The agent obtains percepts from the environment through sensors, makes an internal decision, and produces actions through actuators that change the environment.
This structure looks simple but is difficult to implement. Perception may involve computer vision, speech recognition, or natural language processing. Decision-making may require knowledge, rules, search, planning, or control algorithms. The action module must connect to software interfaces, mechanical devices, or real business processes. Instability in any stage affects the entire agent. Traditional agent development is therefore not a single-feature project but systems engineering that coordinates multiple specialized modules.

As later chapters show, LLM-driven agents do not discard this basic structure. Instead, a large language model greatly simplifies its most difficult parts: understanding, planning, and decision-making. Tool calling, memory, and feedback then form a new type of agent that is easier to develop and iterate.

## Large Language Models and Agents

The preceding section described the general structure of an agent. We now ask why a large language model can become the central component of a new generation of agents. We first briefly review the development of large language models and then see how they fit into the agent loop.

### Development of Large Language Models

At the end of 2022, OpenAI released ChatGPT[^1], a milestone in the development of large language models. For the first time, ordinary users could directly experience an LLM's capabilities in question answering, writing, translation, code generation, and task assistance through natural-language conversation. ChatGPT brought large language models into public view and moved them beyond laboratories and specialist developer tools into education, office work, research and development, customer service, marketing, and many other settings.

The capabilities behind ChatGPT emerged through years of technical accumulation. Deep learning enabled neural networks to learn complex patterns automatically from large datasets. The Transformer architecture used attention to substantially improve long-text processing and parallel training<sup>[2](#ref-vaswani2017attention)</sup>. The GPT family further validated an approach that combines large-scale pretraining with task adaptation. GPT-3 showed that increasing model parameters, training data, and computing resources could produce stronger few-shot learning and general language-processing capabilities<sup>[3](#ref-brown2020language)</sup>. This relationship between scale and capability is commonly called a scaling law.
Scale alone, however, was not enough to make a model a genuinely useful product. Early large language models could generate fluent text but remained weak at understanding user intent, following instructions, refusing unreasonable requests, and responding consistently. ChatGPT's key contribution was to combine large-scale pretraining, instruction tuning, and reinforcement learning from human feedback, making models better at following natural-language instructions. Its breakthrough resulted from the combined maturation of model architecture, data, computing power, training methods, and product interaction.

<a id="fig-llm-development"></a>

![Development of large language models, with ChatGPT as a milestone](./imgs/llm_development.png)

*Figure 1-2. Development of large language models, with ChatGPT as a milestone*

After ChatGPT, large language models entered a period of rapid iteration. Proprietary models such as OpenAI GPT, Google Gemini, and Anthropic Claude continued to improve in general capability and product readiness. Models such as DeepSeek, Alibaba Qwen, and Zhipu GLM advanced open-source ecosystems, Chinese-language performance, coding, and industry applications. Open models lowered barriers to teaching, research, and private enterprise deployment, while proprietary models advanced frontier capabilities, reliable service, and ecosystem integration. The two paths compete and together promote broader adoption.
Recent progress is visible not only in more natural answers but also in a model's ability to act as the core of task execution. Instruction following helps a model understand goals and constraints. Long context enables it to process longer documents, codebases, and conversation histories. Tool calling connects it to search, databases, code interpreters, and business systems. Multimodal capability enables joint processing of text, images, speech, and even video. Deeper reasoning improves complex problem decomposition, comparison of alternatives, and multi-step decision-making. Together, these capabilities provide the technical foundation for LLM-driven agents.

Today's large models broadly include large language models (LLMs), large multimodal models (LMMs), and domain-specific large models (DLMs). LLMs primarily process text and code. LMMs can jointly understand text, images, audio, or video. DLMs are optimized for industries such as medicine, finance, law, and education. Their capability boundaries differ, but all can be connected to an application through an API or local deployment, providing a foundation for understanding tasks, generating plans, and calling tools.
With these categories in mind, we can address the central question of this tutorial: how should we build an LLM-driven agent when the model no longer merely generates text but participates in perception, planning, tool calling, and feedback-based correction?

### Building LLM-Driven Agents

Combining large language models with traditional agent principles provides a simpler and more general approach to agent development. As Figure [1-3](#fig-trad-agent-using-llm) shows, the traditional loop of perception, decision-making, and action remains, but a large language model can assume the most complex decision-making work. In software, environmental information often comes not from physical sensors but from user text, uploaded images, web content, or database records. The model understands this information, considers the task objective, selects the next step, and converts the decision into an executable action through an API or function call.

The model is not generating a response in isolation. It occupies the center of the agent loop. On one side, it receives environmental perceptions such as text, images, or system state. On the other, it connects to external tools such as search, code execution, file operations, data queries, and business interfaces. Developers no longer need to write a complete rule set and decision tree for every scenario. Much of the understanding, reasoning, and task decomposition can be delegated to the model. Development then shifts from writing complex rules to specifying clear objectives, tool interfaces, context organization, and safety constraints.

<a id="fig-trad-agent-using-llm"></a>

![Large language models simplify agent development](./imgs/trad_agent_using_llm.png)

*Figure 1-3. Large language models simplify agent development*

Figure [1-4](#fig-llm-agent) further illustrates an early article's decomposition of an LLM agent into planning, tools, actions, and memory[^2]. Planning breaks a large objective into executable subtasks and adjusts the steps according to feedback. Tools extend the model's own capabilities through resources such as calculators and search engines. Actions are concrete operations that affect the environment, such as sending requests, generating files, modifying data, or controlling a business process. Memory stores short-term context and long-term experience, preserving continuity across multi-turn tasks and enabling reuse in later work. Together, these components form a new agent loop. After the user states a goal, the agent understands the task and current state, creates a plan, selects tools, acts, observes the result, and records useful information in memory. If the result does not meet the goal, it can reflect, revise the plan, and act again. The coordination of reasoning and action emphasized by many agent frameworks is a representative form of this loop.

<a id="fig-llm-agent"></a>

![An LLM-driven agent](./imgs/llm_agent.png)

*Figure 1-4. An LLM-driven agent*

In summary, large language models provide a powerful alternative for the autonomous decision-making brain, the most central and difficult component of agent development. LLM-driven agents retain the basic framework of perception, decision-making, action, and feedback. What changes is the method of decision-making. Earlier agents mainly relied on rules, processes, and policies written in advance. Today's agents can make dynamic judgments from task goals, current state, and tool feedback. They are therefore better suited to open-ended, non-fixed, complex tasks that require language understanding and coordination among multiple tools.
With this framework, we can view an agent application not as a more talkative chatbot but as a task-execution system embedded in a concrete workflow.

### Frontier Agent Applications

An LLM agent's central capability is not simply conversation, but understanding, planning, tool use, and feedback-based correction toward a goal. Applied to real situations, these capabilities produce different kinds of systems. Some agents help programmers write code, some assist with everyday affairs, some understand images, videos, and files, and others enter more complex settings such as robotics, research, and business operations. The examples below offer an intuitive introduction to several common directions.

<a id="fig-agent-applications"></a>

![Frontier agent applications](./imgs/agent-applications.png)

*Figure 1-5. Frontier agent applications*

**Coding agents.**
A coding agent participates in software development. It does more than complete one line of code. It can read project files, understand requirements, modify several files, run tests, and continue fixing problems based on errors. Cursor[^3] and Claude Code[^4] are representative examples. People remain responsible for interpreting requirements, reviewing code, and confirming results.

**Personal assistant agents.**
Personal assistant agents support everyday study, office work, and personal organization. They can organize materials, summarize meetings, plan schedules, retrieve information, generate documents, process email, and complete repetitive operations across applications. Compared with ordinary chatbots, they emphasize continuous action. OpenClaw[^5] is one representative application that helps users build personal AI assistants or digital employees. The closer these agents come to real work, the more carefully privacy, permissions, and human confirmation must be handled.

**Multimodal understanding agents.**
Multimodal agents process text, images, audio, and video together. Instead of seeing only a text prompt, they can reason over different types of material. Typical applications include visual question answering, video summarization, and understanding charts in documents. They help people interpret complex material more quickly, but can still miss details. People should verify important conclusions.

**Automated research agents.**
Automated research agents support research and experimental workflows and remain at an experimental stage. They can retrieve papers, organize related work, propose experimental ideas, write experimental code, analyze results, and generate preliminary reports. They can improve the efficiency of literature review and experimental iteration, but people must still judge whether a research question is valuable, an experiment is fair, and a conclusion is credible.

**Embodied agents.**
Embodied agents bring agent capabilities into robots, autonomous vehicles, drones, or simulated environments. They must understand not only language but also space, objects, and actions. If a user asks a robot to take a cup from the table to the kitchen, for example, it must locate the cup, plan a route, control a robotic arm, and retry after failure. Embodied agents are more difficult than software agents because the physical world contains noise, collision risks, and safety requirements. Many applications remain experimental or limited to specific scenarios, but they demonstrate how agents may move from screens into the physical world.

**One-person companies.**
A one-person company uses multiple agents to perform work that previously required a small team. The point is not for AI to replace people completely but to amplify an individual's capabilities. An entrepreneur might assign market research, product prototypes, software development, promotional copy, customer responses, and data analysis to different agents while retaining responsibility for direction, key decisions, and quality control. This model lowers the barrier to small-scale innovation but requires stronger judgment and accountability from its user.

Although these applications differ in form, they share a foundation: reliably calling a large language model and incorporating its response into a program's workflow. Later chapters progressively add prompt engineering, knowledge bases, tools, memory, and multi-agent collaboration. This chapter begins with a minimal call, the first building block of a digital employee project.

## Hands-On Practice: Environment Setup and Your First LLM Call

<a id="sec-build-llm-dev-env"></a>

Every ambitious system begins with a foundation. The preceding sections introduced the basic ideas behind LLM agents, but every agent system starts with one reliable model call. The goal of this practice is to complete an LLM API call and observe how a role prompt changes the style of a response. Afterward, you should understand the elements of a minimal LLM application: runtime environment, dependencies, credentials, service endpoint, model name, and call script.

Python is one of the most widely used languages for LLM application development. It has a mature ecosystem and a relatively gentle learning curve. Many model services, vector databases, agent frameworks, and data-processing tools provide Python SDKs, so beginning with Python reduces the burden of additional tools. This tutorial assumes familiarity with basic Python syntax, data types, control flow, functions, modules, and file operations. Consult the official Python tutorial[^6] if you need a systematic review.

### Step 1: Install Python and Check Its Version

Python 3.11 or later is recommended. Some SDKs may not install correctly on older versions. Open a terminal on your computer and run:

```bash
python --version
```

### Step 2: Create a Conda Virtual Environment

Use Conda[^7] to create an isolated virtual environment. Virtual environments separate the dependencies of different projects and prevent package versions from interfering with each other. One project may require a newer OpenAI SDK while another depends on an older version. Installing both into the system Python makes later debugging unnecessarily confusing.

```bash
conda create -n agent-book-ch1 python=3.11
conda activate agent-book-ch1
```

With the environment ready, we can enter the project. The immediate goal is not complex functionality but a clear organization of the configuration, dependencies, and code required for a model call. Once this minimal project runs reliably, it provides a base for later sales or customer-service digital employees.

### Step 3: Open the Reference Code Directory

The reference code is in this chapter's [`code/`](./code/README-en.md) directory. This section keeps only the minimal runnable system, without a web service, database, frontend, or agent framework. We first establish the LLM call path and add capabilities in later chapters. The directory structure is:

```text
code/
  .env.example
  .gitignore
  main.py
  requirements.txt
```

### Step 4: Install Dependencies

`requirements.txt` records the project's third-party dependencies. This section uses only two packages: `openai` calls a model service through an OpenAI-compatible interface, and `python-dotenv` reads settings from `.env`.

```bash
cd chapter1_basics/code
pip install -r requirements.txt
```

### Step 5: Configure the Model Service

Create `.env` and configure an API key. An API key is a credential for accessing a model service and must not be written directly into code. Storing it in `.env` separates sensitive configuration from code and makes switching platforms easier. First copy the example file:

```bash
cp .env.example .env
```

Then edit `.env` for your platform. This chapter uses an OpenAI-compatible interface, so Qwen, DeepSeek, and OpenAI can share the same Python code. Only `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` need to change. They specify the access credential, service endpoint, and model name, respectively.

```text
# OpenAI
LLM_API_KEY=your_openai_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini

# DeepSeek
LLM_API_KEY=your_deepseek_api_key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# Qwen
LLM_API_KEY=your_qwen_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
```

Keep only one group of settings in actual use. Model names change as providers update their products. If the program reports that a model does not exist, first check the provider's console for available models. Do not write an API key directly into Python code or commit `.env` to a version-control system such as Git.

### Step 6: Understand and Run the Call Script

Read `main.py`. The script loads settings from `.env`, creates a client, sends messages to the model, and prints its answers. A basic conversation request usually contains two types of information. A `system` message specifies the model's role and behavior, while a `user` message states the current question. This script first asks an ordinary question and then asks a simple question with the model acting as a sales or customer-service digital employee.

The excerpts below come directly from `main.py` and therefore match the code you will run.

First, `require_env()` reads and validates configuration, while `ask_model()` wraps a model request in a reusable function.

```python
def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"请在 .env 中配置 {name}")
    return value

def ask_model(client: OpenAI, model: str, system_prompt: str, user_prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""
```

[View the complete code](code/main.py)

If the API key, endpoint, or model name is missing, `require_env()` immediately reports a clear message instead of waiting for a confusing request failure. `messages` is the conversation context sent to the model. The `system` message describes the model's identity, tone, and response requirements, while the `user` message provides the current task. A model response may contain one or more candidate answers; the example extracts the text of the first.

The main function then reads `.env` and creates the client. `base_url` allows the same calling logic to work with different OpenAI-compatible model platforms. Switching platforms usually requires only a configuration change.

```python
def main() -> None:
    load_dotenv()

    api_key = require_env("LLM_API_KEY")
    base_url = require_env("LLM_BASE_URL")
    model = require_env("LLM_MODEL")

    client = OpenAI(api_key=api_key, base_url=base_url)
```

[View the complete code](code/main.py)

The following excerpt shows the role-prompt interaction. Earlier, the script uses the same `ask_model()` function for an ordinary question, so that call is not repeated here. The principal difference is the `system_prompt`. Modifying it makes the model's expression better suit a sales or customer-service setting.

```python
    role_answer = ask_model(
        client=client,
        model=model,
        system_prompt=(
            "你是一名销售和客服数字员工，回答要礼貌、清晰，"
            "并主动帮助用户理解产品价值。"
        ),
        user_prompt="用户问：你们的智能客服系统适合小公司使用吗？",
    )
    print("\n角色提示词问答：")
    print(role_answer)
```

[View the complete code](code/main.py)

Finally, an entry-point check and exception handler start the main function. Network, authentication, and configuration errors are printed in the terminal to help beginners locate the problem.

```python
if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"运行失败：{exc}")
```

[View the complete code](code/main.py)

This program is not yet a complete agent. It can receive a question and generate an answer, but it does not connect to external tools, continually observe an environment, retain memory, or adjust its actions from execution results. Its purpose is to establish reliable model calling. Later chapters progressively add these capabilities.

The preceding steps created the environment, installed dependencies, configured parameters, and explained the script. The final step is to run the program and inspect its output. This verifies the configuration and reveals the difference between an ordinary answer and a role-conditioned one.

### Step 7: Run the Program and Inspect the Output

After completing the configuration, run the following command from `code/`:

```bash
python main.py
```

If the configuration is correct, the terminal prints two answers. The first is an ordinary response. The second adopts the tone of a sales or customer-service digital employee. This difference shows that a prompt does more than ask a question. It can constrain a model's identity, tone, response structure, and service objective. Modify the question and role prompt in `main.py` and observe how the answer changes.

If the program fails, first confirm that the virtual environment is active, then verify that the dependencies are installed and `.env` contains a real API key, service endpoint, and model name. An authentication error usually means that the API key is incorrect or the corresponding service has not been enabled. A model-not-found error usually means that the model name is incorrect.

## Assignments and Questions

The assignments check that the environment truly works and help connect the minimal call with the concept of an agent. Do not submit only the output. Explain your understanding of model calling, prompts, and agent structure.

1. Complete the practical task in Section [1.3](#sec-build-llm-dev-env). Submit a screenshot of the run, the `main.py` code, and an experimental note of no more than 200 Chinese characters or approximately 120 English words. The screenshot should show both model answers. Briefly explain how the ordinary prompt and the role prompt changed the output. Before submission, confirm that the virtual environment activates normally, the dependencies in `requirements.txt` are installed, `.env` can call the model successfully, and no real API key appears in the submission.
1. Using the chapter's definition of an agent, analyze why `main.py` is closer to a simple chat program than a complete agent. Consider goals, environmental perception, decision-making, action, and feedback.
1. LLM-driven agents commonly connect to tools, memory, and external systems. To extend this script into a sales or customer-service digital employee, list at least three capabilities that must be added and explain the problem each addresses.
1. Choose one of the chapter's application areas: coding agents, personal assistant agents, multimodal understanding agents, automated research agents, or embodied agents. Explain the additional technical requirements beyond this minimal LLM call.

## References

1. <a id="ref-russell2020aima"></a>Stuart Russell, Peter Norvig. Artificial Intelligence: A Modern Approach. Pearson. 2020.

2. <a id="ref-vaswani2017attention"></a>Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N Gomez, et al. Attention is all you need. Advances in neural information processing systems. 30, 2017.

3. <a id="ref-brown2020language"></a>Tom Brown, Benjamin Mann, Nick Ryder, Melanie Subbiah, Jared D Kaplan, Prafulla Dhariwal, et al. Language models are few-shot learners. Advances in neural information processing systems. 33, 1877–1901, 2020.

[^1]: https://chatgpt.com
[^2]: https://lilianweng.github.io/posts/2023-06-23-agent
[^3]: https://cursor.com
[^4]: https://code.claude.com
[^5]: https://openclaw.ai
[^6]: https://docs.python.org/3/tutorial/index.html
[^7]: Note: Conda is a Python virtual environment and package management tool. See https://anaconda.org/anaconda/conda for details.

---

[Back to Contents](../README-en.md) | [Next Chapter →](../chapter2_chatbot/README-en.md)
