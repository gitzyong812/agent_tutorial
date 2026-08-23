[中文](./README.md) | [English](./README-en.md)

[← Previous Chapter](../chapter1_basics/README-en.md) | [Back to Contents](../README-en.md) | [Next Chapter →](../chapter3_rag/README-en.md)

> Companion code for this chapter: [open the code directory](./code/README-en.md)

# A Basic ChatBot Digital Employee

The previous chapter completed our first LLM API call. The program could ask a model a question and receive an answer, but each call was independent and the model knew nothing about earlier interactions.
This chapter turns those isolated exchanges into a ChatBot digital employee capable of continuous conversation. With a clear role, service objective, and conversation rules, it can answer simple questions and guide a process within a defined scenario. A sales digital employee, for example, learns about a user's needs, answers questions about a product, and guides the next step. A customer-service employee identifies a problem, explains the procedure, and recommends human assistance when necessary. It is not yet a fully capable agent, but it has the basic form of a digital employee.

A basic ChatBot has three main parts. Model call parameters determine which model is used and how it generates an answer. Conversation history gives the model the preceding exchange again. The system prompt defines the digital employee's identity and working boundaries. The prompt explains what to do, the history supplies what has already been said, and model parameters regulate how to answer. This chapter introduces each principle and concludes by building a basic ChatBot.

After completing this chapter, you should be able to:

1. Explain the difference between a basic ChatBot digital employee and an ordinary LLM question-answering program.
1. Understand how role definitions, task objectives, constraints, and examples contribute to prompt engineering.
1. Conduct multi-turn conversations while retaining and managing the conversation context.
1. Design common questions, answers, and basic conversation flows for sales or customer-service scenarios.
1. Build a minimal runnable ChatBot digital employee from the Chapter 1 code.

## Model Call Parameters

Good prompts and conversation content are not enough to make a ChatBot behave as expected. Model call parameters also need reasonable settings. They do not replace task design, but they affect stability, length, and expression.
Parameter names, ranges, and defaults vary across model services, so actual development should follow the documentation of the service in use<sup>[1](#ref-openaiChatCompletions)</sup>. The following parameter categories are broadly applicable.

**Model.** The model name selects the model that answers the current request, much like choosing an executor for the ChatBot. Stronger models are generally better at complex instructions and long text but may cost more and respond more slowly. For a basic ChatBot, begin with a general model that balances speed, cost, and quality, then test it against representative questions.

**Temperature.** `temperature` controls randomness. At a lower value, the model favors common, high-confidence expressions, so repeated answers to the same question tend to be similar. At a higher value, it explores more possible expressions and produces more varied answers. Knowledge questions, procedural instructions, and information extraction generally favor lower temperatures for stability and accuracy. Copywriting and brainstorming may benefit from a higher value. Temperature affects expression but cannot guarantee correctness.

**Top P.** `top_p` also controls diversity. When generating the next token, a model considers many candidates. `top_p` determines how broad a set of candidates may be considered. A lower value concentrates on the most likely candidates, while a higher value permits greater variety. Temperature and Top P have similar purposes. Beginners should usually treat one as the main control rather than changing both substantially at once.

**Maximum Output Length.** Services may use `max_tokens`, `max_completion_tokens`, or a similar field to limit generated tokens. This sets an upper bound on the response, preventing excessive length and helping control cost. A one- or two-sentence summary can use a short limit, while a step-by-step explanation needs more room.

**Frequency Penalty and Presence Penalty.** Both settings reduce repetition. Frequency penalty makes a token harder to repeat as its frequency in the answer rises. Presence penalty lowers the probability of repeating a token once it has appeared at all. Increase them moderately when a model repeatedly uses the same words or when more varied expression is desirable. They assist with style but do not replace a clear task description.

Table [2-1](#tab-chatbot-default-parameters) gives a common starting configuration for a general ChatBot answering everyday questions. Such conversations usually need stable, concise, understandable answers, so temperature is low while Top P, stop sequences, and both penalties retain common defaults.

<a id="tab-chatbot-default-parameters"></a>

*Table 2-1. Common initial parameters for a general conversational ChatBot*

| **Parameter** | **Example** | **Reason** |
| --- | --- | --- |
| Model<br> `model` | `deepseek-v4-pro` | Select a model suited to general question answering. Replace it with an equivalent model from the connected platform. |
| Temperature<br> `temperature` | `0.2` | Reduce randomness so repeated calls for the same question produce more stable answers. |
| Top P<br> `top_p` | `1.0` | Keep the common default and control diversity mainly through temperature, making its effect easier to observe. |
| Maximum output length<br> `max_tokens` | `500` | Provide enough room for common questions and brief explanations while avoiding excessive answers and cost. |
| Frequency penalty<br> `frequency_penalty` | `0` (default) | Apply no extra penalty initially. Adjust slightly only when the model clearly repeats words or sentence patterns. |
| Presence penalty<br> `presence_penalty` | `0` (default) | Do not reduce the probability of previously used words, allowing the answer to remain focused rather than introducing unrelated content merely for variety. |

Table [2-1](#tab-chatbot-default-parameters) is a starting point, not a fixed standard. Prepare a representative question set and change one parameter at a time. Compare correctness, completeness, tone, and cost. This produces settings suited to the actual business rather than a single demonstration.

#### Example: Setting LLM Call Parameters in Python

The following excerpt shows only the generation parameters[^1]. Assume that `client` has been initialized and `messages` already contains system and user messages. Its keyword arguments correspond directly to Table [2-1](#tab-chatbot-default-parameters).

```python
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=messages,
    temperature=0.2,
    top_p=1.0,
    max_tokens=500,
    frequency_penalty=0,
    presence_penalty=0,
)
```

Setting `temperature` to `0.2` makes general question answering more stable. `top_p` and the two penalties remain at their defaults so that the effect of temperature can be observed first. The next section builds on the `messages` list and explains how to append user and assistant messages after each turn.

Output-length field names differ among platforms. This example uses `max_tokens`, which many compatible interfaces support. Some newer OpenAI models and other services require `max_completion_tokens`. If a call reports an unsupported parameter, consult the current platform documentation and change only the corresponding field rather than modifying several generation settings at once.

## How Multi-Turn LLM Conversations Work

The preceding parameters control characteristics such as randomness and length, but they do not make a model retain an earlier exchange. For most LLM APIs, every call is an independent request. If only the user's latest question is sent, the model cannot know what “it,” “the second step,” or “the previous plan” refers to. Continuity comes from the application storing earlier messages and sending them again.

### Structure of a Multi-Turn Conversation

A multi-turn ChatBot should therefore use a structured message sequence rather than concatenating the entire conversation into one block of text. Each message contains at least a **role** and **content**. The role says who produced the message and what purpose it serves, while the content records the instruction, question, or answer. Messages remain in chronological order. The system message usually comes first, followed by alternating user questions and assistant answers. A basic ChatBot commonly uses three roles.

**System message.** A developer sets the system message to define the ChatBot's position, task scope, and response rules. It acts as a job description for the digital employee, usually appears at the start of the sequence, and remains stable throughout a session. It may require the ChatBot to answer only from supplied materials and to disclose uncertainty or ask a follow-up question when information is insufficient.

**User message.** User messages record the questions, additional information, and new requirements provided in each turn. They tell the model what to do now and drive the conversation forward.

**Assistant message.** Assistant messages record earlier model answers. Retaining them lets the model know what it has already explained, follow a user's subsequent question, and reduce repetition and contradiction.

The following example shows a basic message sequence. In the second turn, the user says only “the second stage,” but the earlier user and assistant messages make the reference clear. Role labels and message order work together to create this continuity.

```text
system:     你是学习规划助手。请根据用户的学习目标给出清晰、可执行的建议；不确定的信息要明确说明。
user:       我想在两个月内学会 Python，应该怎样安排？
assistant:  可以分为三个阶段：先掌握基础语法，再练习常用数据处理，最后完成一个小项目。
user:       那第二阶段应该先学什么？
assistant:  第二阶段可以先学习列表、字典等常用数据结构，再练习读取、整理和分析简单数据。
...
```

### How an LLM Processes Multi-Turn Conversations

One turn is implemented as a continually updated loop. The program first creates a message list containing a fixed system message. When the user provides input, it appends a `user` message. After the model generates an answer, the program appends that answer as an `assistant` message for the next call. The model does not independently retain memory after a request ends. Its apparent memory comes from the application supplying the necessary context again.

Messages are stored as role-and-content structures, but the model ultimately receives encoded text or a token sequence. Before a call, the interface or framework converts the message list into the input format required by the model. This is commonly called processing a **chat template**; some local model frameworks provide a function named `apply_chat_template`. The template preserves roles and order while organizing the messages into a format the model recognizes. Specific markers differ among models, so developers should use the template supplied by the model or framework rather than manually joining text. Cloud APIs usually perform this conversion internally, requiring only a structured message list from the developer.

<a id="fig-llm-multi-turn"></a>

![How an LLM processes a multi-turn conversation](./imgs/llm_multi-turn.png)

*Figure 2-1. How an LLM processes a multi-turn conversation*

Figure [2-1](#fig-llm-multi-turn) illustrates the first two turns. The first call contains only the system message and the user's initial question. The program stores the model's answer. When the user asks the second question, the new input includes the first question and answer, allowing the model to understand what “the second stage” means.

Conversation history cannot grow without limit. A model can read only its context window, and longer history generally increases cost and response time. A suitable strategy for a basic ChatBot is to retain the fixed system message and a limited number of complete recent turns. In a long session, older content can be compressed into a short summary and sent alongside recent messages. Key facts such as names, product models, and order numbers are better stored in structured fields that the program can read and update directly.
Context management is not about placing the entire history unchanged into a prompt. It is about showing the model the most relevant and reliable information for the current task. Prioritize system rules, facts needed for the current question, and recent conversation. A new user request must not override business boundaries defined by the system. If a user asks the ChatBot to invent a price, for example, system requirements concerning truthfulness and human escalation should still take priority.

## Prompt Engineering

The preceding section showed how a message list retains context. Context answers what has already been said, but the model must also know what role to perform, what information it may use, and how to handle uncertainty. A prompt states these requirements explicitly. Prompt engineering organizes input around a task objective<sup>[2](#ref-openaiPromptEngineering)</sup> and can be understood as a digital employee's job description and operating rules.

### Prompt Elements

A complete prompt need not be long, but it should clarify four matters: the task, the information available for the task, the input to process now, and the required form of the answer.
These correspond to instructions, context, input data, and output indicators. Separating them helps a developer determine whether a poor answer requires changing the task, adding information, or adjusting the output format.

An **instruction** states what the model should do, such as answering a user's question from product information or classifying feedback as logistics, after-sales service, or product quality. **Context** supplies necessary background such as product specifications, service procedures, current order status, and confirmed user needs. **Input data** is the specific content to process, usually the user's current question. An **output indicator** defines the answer format, perhaps requiring a conclusion followed by two supporting points or only a fixed set of fields. The role is normally part of the instruction, constraining the employee's position and tone rather than standing apart from these elements.

<a id="fig-prompt-elements"></a>

![Prompt elements and their organization in a program](./imgs/prompt_elements.png)

*Figure 2-2. Prompt elements and their organization in a program*

In ordinary conversation, prompts can be relatively free-form as long as they make the instructions, context, input, and output requirements clear.
Programs benefit from separating this information. The role and stable rules usually belong in the system message. Product details and order state form the context. The user's current question is the input. Output indicators constrain the response format. This organization is readable and allows a business-information change to update only the relevant part. Figure [2-2](#fig-prompt-elements) maps these elements to system and user messages.

The following headphone presales prompt combines these elements. It is not intended to sound elaborate. It tells the model what information to use, what work to perform, and how to deliver the result.

```text
系统消息：
角色与任务：你是面向学生用户的耳机售前咨询助手。依据已知资料回答问题，表达友好、简洁。
产品资料：无线耳机，单次续航约 8 小时，支持 IPX5 级防水，有白色和深灰色两种颜色。
回答要求：资料未说明时，明确说明无法确认；不得补充不存在的功能；先直接回答，再用一两句话补充依据。

用户消息：
我每天坐地铁通勤，想知道这款耳机是否适合使用？
```

Here, role and task define who the model is and what it should do. Product information is context. The user's commute is the current input. Response requirements define the boundary and basic structure. A prompt does not need to be perfect immediately. Begin with a clear task, information, and output format. Add a role, constraints, or examples when testing reveals instability. Add business information that genuinely affects the answer instead of accumulating abstract requirements. If the model invents features, define trusted information and the treatment of unknowns. If answers are too long, specify a word limit, structure, or fields.

### Prompt Design Techniques

Having identified the elements, we now consider how to write them effectively. The objective is not length but reducing what the model must guess. An effective prompt clarifies **who acts**, **what to do**, **what information to use**, **what is prohibited**, and **what qualifies as a good result**. Ambiguity in any area encourages the model to fill gaps with plausible content and drift from the intended answer. Figure [2-3](#fig-prompt-tricks) summarizes common techniques. Select and combine them according to the task.

<a id="fig-prompt-tricks"></a>

![Overview of prompt design techniques](./imgs/prompt_tricks.png)

*Figure 2-3. Overview of prompt design techniques*

In practice, write a short first version and test it with real questions. If tone is unstable, make the role more specific. If the answer drifts, clarify the task and steps. If it contains unreliable information, define the allowed sources and constraints. If the format varies, add output requirements or examples. Targeted changes are more effective than accumulating vague statements such as “answer carefully.” Five common techniques follow.

#### Role Definition

A role tells the model the identity from which it should work and primarily stabilizes tone, focus, and boundaries. An effective role description usually includes the **position**, **audience**, **scope**, and **communication style**. A presales scenario might say: “You are a headphone presales assistant serving student customers. Introduce features and answer common questions from product information in a friendly tone without making excessive promises.”

Be specific without piling up personality adjectives. “You are professional customer service” does not identify the allowed information or output format. Adding irrelevant qualities such as enthusiastic, intelligent, and patient does not fill those gaps. A role must work with the objective, constraints, and context. It answers who performs the task, while instructions and constraints define what to do and where to stop.

#### Clear Instructions

An objective states what the digital employee helps a user accomplish. In sales, it may introduce a product, identify needs, and recommend an appropriate option. In customer service, it may explain a procedure, diagnose a problem, and collect essential information. To make an objective testable by both model and developer, organize it as **object + action + necessary steps + output form**.

Instead of “answer the user well,” write: “First confirm which product the user is asking about. If the information contains the answer, respond in two or three sentences. If it is insufficient, ask one clarifying question.” For multi-step tasks, state the order and expected result of each step. Define an output format such as three fields named Issue Assessment, Recommended Action, and Human Escalation. This reduces guessing and makes each requirement testable.

#### Constraints

Constraints control boundaries. They may forbid inventing policies, promising unconfirmed prices, or requesting unnecessary personal information, and require human escalation for high-risk questions. They prevent the model from crossing business boundaries in pursuit of the task.

Write constraints as **trigger + prohibited behavior + alternative action**. For example: “If the material does not cover the return policy, do not answer from speculation. State that the current material cannot confirm it and recommend contacting human customer service.” This both forbids an action and gives an appropriate next step. In high-risk fields such as finance, medicine, and law, prompts are only the first control layer. Real systems also need permissions, reviewed knowledge, logs, and human review. Written constraints alone do not provide complete safety.

#### Reference Examples

Reference examples, also called few-shot examples, supply pairs of inputs and ideal outputs so the model can learn the expected response pattern concretely. Unlike a zero-shot prompt containing only instructions, few-shot prompting places abstract requirements into specific conversations. The model sees how users ask questions, what tone and structure an answer should use, and which expressions are unacceptable. This works especially well for fixed classification, standardized formats, and specific tones.

<a id="fig-fewshot-example"></a>

![Few-shot prompting uses positive and negative examples to guide compliant replies](./imgs/fewshot.png)

*Figure 2-4. Few-shot prompting uses positive and negative examples to guide compliant replies*

In Figure [2-4](#fig-fewshot-example), the instruction requires customer-service replies to begin with “Dear customer,” and maintain a friendly, professional tone. Example 1 gives a compliant answer to a discount question. Example 2 supplies a counterexample that omits the required opening and identifies the problem. For a new return question, the model follows the positive example while avoiding the counterexample, producing a useful reply with the required tone. Positive examples demonstrate what to do, while negative examples identify unacceptable behavior.

A few examples are enough if they cover representative questions, tones, and procedures. For beginners, three to five high-quality question-answer examples are often more effective than a complex prompt. Examples must agree with real business rules and be updated with policy, product, or campaign changes so the model does not learn from obsolete or contradictory cases.

#### Chain-of-Thought Prompting

Chain-of-Thought (CoT) prompting asks a model to complete necessary intermediate reasoning before giving a conclusion<sup>[3](#ref-wei2022chain)</sup>. It suits calculations, comparisons among conditions, and multi-step judgments. A simple factual question such as whether an item ships free needs only a direct answer. Calculating an order total after a threshold discount, coupon, and shipping fee requires sequential application of rules.

<a id="fig-cot"></a>

![Using a chain-of-thought prompt to calculate an e-commerce order total](./imgs/cot.png)

*Figure 2-5. Using a chain-of-thought prompt to calculate an e-commerce order total*

The left side of Figure [2-5](#fig-cot) shows the complete prompt. The task defines responsibility for calculating the order amount. “Let's think step by step” prevents an immediate unsupported result. Explicit steps fix the order: total list prices, apply the threshold discount, subtract the coupon, and add shipping. Product prices, discount rules, and the user's question supply evidence for every calculation.

On the right, the model first obtains a list-price total of RMB 218, then applies the discount, coupon, and shipping to reach RMB 176. Showing the calculation lets the user inspect whether the rules were applied correctly and helps the developer find the step containing an error. “Let's think step by step” is a short zero-shot CoT instruction, but real business tasks are safer when the steps and output format are also explicit. CoT prompting does not replace data verification. Prices, promotions, and shipping must still come from reliable sources.

### Prompt Examples for Common Tasks

Roles, instructions, constraints, examples, and chain-of-thought are not all required every time. Different tasks emphasize different information. Summaries emphasize focus and length, classification emphasizes category boundaries, and question answering emphasizes evidence. Begin with the task objective, then add the input, rules, and output format needed to complete it. Table [2-2](#tab-prompt-task-examples) summarizes common basic ChatBot tasks. Prompt Focus identifies essential information, while Example gives a sentence that can be adapted directly.

<a id="tab-prompt-task-examples"></a>

*Table 2-2. Common basic ChatBot tasks and prompt examples*

| Task Type | Objective | Prompt Focus | Example |
| --- | --- | --- | --- |
| Summarization | Compress long material into an accessible explanation. | Define the reader, length, and information that must be retained. | Summarize the following after-sales policy as three user instructions, retaining time limits and exceptions. |
| Information extraction | Extract specified fields from text. | List fields, output structure, and treatment of missing values. | Extract the order number, product model, and issue type from the message. Write “not provided” for missing information. |
| Grounded Q&A | Answer from known material. | Limit the sources and define how to handle insufficient information. | Answer only from the following product information. If it does not answer the question, tell the user and recommend a source to consult. |
| Text classification | Assign input to a finite category. | Define categories, criteria, and confusing boundaries. | Classify the message as logistics, quality, after-sales, or other. Treat product damage as a quality issue. |
| Continuous conversation | Complete a consultation or resolve a problem over multiple turns. | Define the role, progression, and when to ask or escalate. | Learn the need first, then explain an option. Ask when information is missing and recommend human service when the problem cannot be handled. |
| Code generation | Generate, explain, or modify a program. | Specify the language, environment, input/output, and acceptance conditions. | Use Python to retain the latest five conversation turns. End the program when the input is `quit`. |
| Conditional judgment and recommendation | Compare conditions and recommend an option. | List decision evidence, constraints, and the format for reasons. | Recommend one option from the budget, usage scenario, and product information, and give two reasons. |

Every example can be organized as task, evidence, rules, and output. State the task, provide allowed information, define boundaries, and specify the output form. You do not need to cover every task immediately. Start with frequent tasks such as grounded Q&A or continuous conversation, add rules and examples for confusing cases discovered in real questions, and expand gradually.

## Hands-On Practice: Build a Basic ChatBot Digital Employee

### Step 1: Understand the Basic ChatBot Framework

This practice iterates on Chapter 1's direct model call to build a minimal runnable web-based ChatBot digital employee. The preceding sections discussed model parameters, multi-turn context, and prompt engineering. Here, model configuration selects the LLM, digital employee configuration organizes the system prompt, and session messages determine how much earlier conversation the model can see.

The companion code is in `chapter2_chatbot/code/`. It provides Chat, Model Configuration, and Digital Employee Configuration pages. The focus is not the web framework or database but the relationship among three configurations. Model configuration answers which model to call. Digital employee configuration answers whom the model should represent, what information it may use, and what rules it must follow. Session history answers what was said before the current turn. These are the chapter's theoretical main line.

Figure [2-6](#fig-chapter2-agent-config-screen) shows the digital employee configuration page. Role, task, information, constraints, and output format from prompt engineering become editable fields. Parameters such as `temperature`, `top_p`, and `max_tokens` appear in the same form so learners can observe how they affect response style.

<a id="fig-chapter2-agent-config-screen"></a>

![Configuration interface for a basic ChatBot digital employee](./imgs/chapter2_agent_config_screen.png)

*Figure 2-6. Configuration interface for a basic ChatBot digital employee*

The following excerpt summarizes the most important fields. `role`, `service_goal`, `business_context`, `constraints`, and `output_instruction` correspond to prompt elements. `temperature`, `top_p`, `max_tokens`, and `history_turns` control model calls and context. How they are stored in the database is not a focus of this chapter.

```python
agent_config = {
    "role": "你是保险公司内部的政策咨询专家。",
    "service_goal": "依据业务资料回答政策类问题。",
    "business_context": "这里填写可引用的产品、条款或流程资料。",
    "constraints": "资料未覆盖的内容，明确说明无法确认。",
    "output_instruction": "先直接回答，再简要说明依据。",
    "temperature": 0.2,
    "top_p": 1.0,
    "max_tokens": 500,
    "history_turns": 5,
}
```

The current system is a local teaching example. API keys, database files, and configuration files must not be committed to a public repository. A real business system requires stricter credential management, access control, and audit logs, which are outside this chapter.

### Step 2: Observe Prompt Assembly and Short-Term History

A basic ChatBot should place variable business information in configuration rather than hard-code every rule. On each model call, it assembles those fields into a system prompt. The following code from `app/llm.py` organizes the role, objective, business information, constraints, and output requirements, then adds a general rule: answer only from configured information; when it is insufficient, say so and recommend human verification. This matches the task, evidence, rules, and output structure introduced earlier.

```python
def build_system_prompt(agent: models.AgentConfig, language: str = "zh") -> str:
    sections = [
        ("角色", agent.role),
        ("任务目标", agent.service_goal),
        ("业务资料", agent.business_context),
        ("约束条件", agent.constraints),
        ("输出要求", agent.output_instruction),
    ]
    parts = [f"# {title}\n{content.strip()}"
             for title, content in sections if content.strip()]
    parts.append(
        "# 通用规则\n"
        "只依据上述业务资料回答；资料未覆盖的内容，明确说明无法确认，"
        "不要编造，并建议用户向人工进一步确认。"
    )
    parts.append(_LANGUAGE_HINT.get(language, _LANGUAGE_HINT["zh"]))
    return "\n\n".join(parts)
```

Multi-turn conversation remains minimal. This chapter introduces no long-term memory, summary memory, or knowledge retrieval. It takes the latest `history_turns` turns from the current session and sends them with the current input. Because one turn contains a user message and an assistant message, the code selects `history_turns * 2` messages.

```python
def build_messages(agent, history, user_input, language="zh") -> list[dict]:
    previous = history[-(agent.history_turns * 2):] if agent.history_turns > 0 else []
    return [
        {"role": "system", "content": build_system_prompt(agent, language)},
        *[{"role": m.role, "content": m.content} for m in previous],
        {"role": "user", "content": user_input},
    ]
```

The web page sends a user message to the backend, which calls the model and returns the answer. Think of this as three steps: load the current digital employee configuration, load the latest history, and call the model with the current input. This chapter requires you to run and observe the interface, not master streaming display, API design, or persistence.

### Step 3: Configure an Insurance Consultation Employee

With the general framework ready, the practice configures an insurance consultation example. An administrator can define the employee as an Insurance Policy Consultant or Insurance Sales Script Coach, place permitted products, terms, or script examples under business information, and forbid promises about returns, claims, or unconfirmed terms. Insurance rules then belong to this employee's configuration rather than being fixed rules for every ChatBot.

Figure [2-7](#fig-chapter2-chat-session-screen) shows a continuous conversation. In the first turn, the user asks whether a claim can be guaranteed, and the assistant follows its constraints by avoiding a definite promise. In the second, the user asks about a disease definition absent from the material. The assistant uses the earlier consultation context and recommends checking formal terms or asking staff. The system has short-term multi-turn context, which is not the same as long-term memory or knowledge-base Q&A.

<a id="fig-chapter2-chat-session-screen"></a>

![Multi-turn interface for a basic ChatBot digital employee](./imgs/chapter2_chat_session_screen.png)

*Figure 2-7. Multi-turn interface for a basic ChatBot digital employee*

An insurance consultation flow should combine free conversation with fixed rules. A completely fixed flow feels mechanical, while completely free conversation can drift from business goals. Begin with one simple product or service, list about ten common questions, and organize them into a basic test set. Focus on whether the employee refuses to invent absent information, avoids promises about returns or claims, and uses earlier context in follow-up questions.

### Practice Tasks

1. In `chapter2_chatbot/code/`, install dependencies, run `uvicorn app.main:app --reload`, open the local web page, and confirm access to Chat, Model Configuration, and Digital Employee Configuration.
1. Configure an OpenAI-compatible model service with at least an endpoint, model name, and API key. Use Test to verify the connection.
1. Create or edit a basic ChatBot. Complete the role, task objective, business information, constraints, and output requirements, and observe how they form the system prompt.
1. Compare parameter settings with the same questions. Lower and raise `temperature` to observe stability and variety. Adjust `history_turns` to see whether the second and third questions still connect to earlier context.
1. Configure the ChatBot as an insurance consultation employee. Define factual scope and risk boundaries in its information and constraints, publish it, and create a session.
1. Prepare at least ten insurance questions covering insufficient information, promised returns, claim conclusions, and follow-up questions. Check that the system maintains its role, uses supplied information, and recommends human confirmation.

### Expected Outcomes

Submit a basic ChatBot practice report containing screenshots, a prompt design explanation, model parameter records, and a test-question list. Explain how model configuration, digital employee configuration, and conversation history affect answers. State the current capability boundary: configurable prompts, model parameters, and short-term multi-turn context are supported, but the system cannot retrieve an enterprise knowledge base, call a business system, or form long-term memory. Chapter 3 adds knowledge retrieval, Chapter 4 introduces tools and memory, and later chapters discuss multi-agent orchestration and human confirmation.

## Assignments and Questions

1. Choose a specific product or service and design a role prompt for a sales or customer-service digital employee.
1. Write at least ten common questions and answers, identifying the business information each requires.
1. Run the basic ChatBot for at least three turns. Analyze whether its role remains consistent and identify which answers depend on conversation history.
1. Compare two model parameter settings, such as lower and higher `temperature`, and observe changes in stability and expression.
1. Explain why a basic ChatBot cannot directly solve complex business problems. Consider knowledge updates, tool calling, long-term memory, access control, and human review.

## References

1. <a id="ref-openaiChatCompletions"></a>OpenAI. [Chat Completions API Documentation](https://platform.openai.com/docs/guides/text). 2026.

2. <a id="ref-openaiPromptEngineering"></a>OpenAI. [Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering). 2026.

3. <a id="ref-wei2022chain"></a>Jason Wei, Xuezhi Wang, Dale Schuurmans, Maarten Bosma, Fei Xia, Ed Chi, et al. Chain-of-thought prompting elicits reasoning in large language models. Advances in neural information processing systems. 35, 24824–24837, 2022.

[^1]: Based on the [OpenAI Python API library](https://github.com/openai/openai-python).

---

[← Previous Chapter](../chapter1_basics/README-en.md) | [Back to Contents](../README-en.md) | [Next Chapter →](../chapter3_rag/README-en.md)
