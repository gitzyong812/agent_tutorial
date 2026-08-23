[中文](./README.md) | [English](./README-en.md)

[← Previous Chapter](../chapter2_chatbot/README-en.md) | [Back to Contents](../README-en.md) | [Next Chapter →](../chapter4_agent_memory_tools/README-en.md)

> Companion code for this chapter: [open the code directory](./code/README-en.md)

# A Knowledge-Augmented RAG Digital Employee

Chapter 2 built a basic ChatBot digital employee. It can conduct continuous conversations using a role prompt, model parameters, and short-term history, but its knowledge remains limited. Some comes from the model's training, and some is written into the system prompt. This works when the material is small and the rules are stable. Real business settings are more difficult: documents, processes, and versions change, while internal knowledge may be scattered across web pages, PDFs, spreadsheets, and databases. Placing everything in a prompt makes it increasingly long and difficult to maintain.

This chapter introduces Retrieval-Augmented Generation (RAG). After a user asks a question, the system retrieves relevant material from an external knowledge base and sends it to the LLM with the question, allowing the model to answer from visible evidence. The digital employee no longer relies only on model memory. It can work with documents, knowledge bases, business rules, and structured data. RAG is a key step from a basic ChatBot to a knowledge-oriented digital employee.

After completing this chapter, you should be able to:

1. Explain the basic idea of RAG and how it differs from a basic ChatBot.
1. Understand the relationships among preprocessing, chunking, extraction, normalization, embedding, indexing, and augmented generation.
1. Design a knowledge-base organization scheme for a general business scenario.
1. Compare the appropriate uses of keyword, vector, graph, and SQL retrieval.
1. Explain why RAG reduces fabrication risk without eliminating errors completely.
1. Extend the Chapter 2 ChatBot into a RAG digital employee with knowledge retrieval.

## What Is RAG?

Before an LLM generates an answer, RAG retrieves relevant content from an external knowledge base and supplies the results as context. RAG was first systematically discussed as a method that combines parametric memory with non-parametric external knowledge<sup>[1](#ref-lewis2020rag)</sup>. Parametric memory is the knowledge fixed in a trained model's parameters. It is broad but difficult to update and cite. Non-parametric external knowledge includes independently maintained documents, web pages, databases, and knowledge graphs that can be updated, traced, and reviewed.

The point of RAG is therefore not to make the model memorize more, but to make it consult sources before answering. A basic ChatBot resembles a closed-book response based mainly on model knowledge and prompts. A RAG digital employee resembles an open-book response that retrieves material first. This apparently simple change alters the employee's knowledge sources, system boundary, and maintenance process.

<a id="fig-rag"></a>

![Knowledge construction, retrieval, and generation in a RAG digital employee](./imgs/rag.png)

*Figure 3-1. Knowledge construction, retrieval, and generation in a RAG digital employee*

Figure [3-1](#fig-rag) shows the full workflow. This chapter divides it into three stages. Offline knowledge-base construction turns raw material into retrievable, traceable, maintainable knowledge units. Knowledge retrieval finds candidate material in vector stores, graph databases, relational databases, or search engines. Online augmented generation organizes a small set of high-quality results in a prompt so the LLM answers from those materials.

The main system flow changes between Chapters 2 and 3. A basic ChatBot focuses on speaking according to a role and context. A RAG digital employee also determines which external material supports an answer. The new stage is **retrieval**. The employee must find information before composing the answer. When the material does not cover a question, the system should say that it cannot confirm the answer instead of filling the gap from general experience.

### Why Do We Need RAG?

RAG offers four main benefits to a digital employee.

**First, knowledge can be updated dynamically.** A trained model does not automatically update as the world changes, while policies, product information, technical documentation, and procedures change frequently. Updating a RAG knowledge base is usually lighter than retraining a model and better aligned with information management. Once new material is indexed, the next retrieval can use it.

**Second, answers can follow designated sources more closely.** A basic ChatBot may give generic advice even in a natural tone. RAG places retrieved document chunks into context so the model can focus on specified material. For a permissions question, for example, the system should retrieve the current manual instead of asking the model to guess from general experience.

**Third, evidence is easier to inspect.** RAG can record retrieved chunks, document titles, section locations, and update times. Developers, business staff, and administrators can see exactly which material the employee used and identify missing sources, retrieval errors, or misinterpretations.

**Fourth, prompts can remain concise.** Chapter 2 showed that prompts contain a role, task, information, constraints, and output requirements. Placing all business material in the system prompt makes it unwieldy and increases the risk that the model overlooks important points. RAG filters first and supplies fewer, more relevant materials.

### RAG Compared with a ChatBot

Both basic ChatBots and RAG digital employees require model parameters, system prompts, and multi-turn history. The difference is whether knowledge retrieval occurs before answering. Table [3-1](#tab-chatbot-rag-diff) summarizes the distinction.

<a id="tab-chatbot-rag-diff"></a>

*Table 3-1. Differences between a basic ChatBot and a RAG digital employee*

| **Dimension** | **ChatBot** | **RAG** |
| --- | --- | --- |
| Knowledge source | Primarily model knowledge and material written into the prompt. | Model capabilities, the system prompt, and results retrieved from an external knowledge base. |
| Suitable tasks | Simple Q&A, fixed-process guidance, and text rewriting. | Knowledge-base Q&A, policy explanation, document assistance, and data queries. |
| Update method | Modify information in prompts or code. | Update knowledge documents, then chunk and index them again. |
| Risk control | Use prompt constraints to discourage fabrication. | In addition to constraints, require answers to follow retrieved chunks. |
| Main difficulty | Role, tone, and conversation-history management. | Document quality, chunking, retrieval accuracy, and presentation of evidence. |

RAG is not a universal fact checker. If a knowledge base is outdated, chunks are poorly divided, or retrieval results are irrelevant, the model can still be wrong. RAG makes reliable material easier for a model to access but cannot replace source review, business rules, or human verification.

## Building an Offline Knowledge Base

Having established why external material is needed, we now consider how it enters a knowledge base. Figure [3-2](#fig-knowledge) shows the overall process. Raw sources follow different processing paths according to their form. Preprocessing, extraction, normalization, and indexing produce vector, graph, and structured knowledge. The RAG system then retrieves, augments, and generates from this knowledge. The purpose is not merely to store material but to create knowledge units with clear content, metadata, provenance, and validity for later retrieval, citation, and maintenance.

<a id="fig-knowledge"></a>

![Framework for building an offline knowledge base](./imgs/knowledge.png)

*Figure 3-2. Framework for building an offline knowledge base*

### Knowledge Sources and Boundaries

Sources may include documents, web pages, spreadsheets, databases, FAQs, knowledge graphs, logs, or historical conversations. Before selecting them, define the boundary: which material may be cited, which is for internal use only, and which is outdated or requires human confirmation. A published manual may enter the knowledge base, while drafts and old versions should be isolated or clearly marked. Without boundaries, obsolete material may produce answers that appear grounded but are unreliable.

Sources can be divided into three types. Unstructured data has no fixed fields or table structure and conveys meaning through language and layout, as in documents, web pages, and OCR text. Semi-structured data has some hierarchy, tags, or relationships without a completely uniform format, as in FAQs, JSON, XML, knowledge graphs, and tickets. Structured data has explicit fields, types, and relationships, as in spreadsheets, relational databases, and warehouse tables.

<a id="tab-rag-knowledge-sources"></a>

*Table 3-2. Three types of data in a RAG knowledge base*

| **Data Type** | **Typical Sources** | **Core Characteristics** | **Processing Focus** |
| --- | --- | --- | --- |
| Unstructured | Documents, web pages, and image OCR text. | Meaning is expressed through natural language and layout. | Parsing and cleaning, text chunking, and vector indexing. |
| Semi-structured | FAQs, JSON, XML, knowledge graphs, and ticket records. | Some hierarchy, labels, or relationships, but no uniform format. | Entity normalization, relationship extraction, and graph indexing. |
| Structured | Spreadsheets, relational databases, and business tables. | Explicit fields, types, and table relationships. | Field semantics, permissions, and query interfaces. |

Table [3-2](#tab-rag-knowledge-sources) summarizes the three categories. Beginners can start with well-structured unstructured documents, then gradually add graph data, spreadsheets, and databases.

### Building Unstructured Knowledge

Unstructured knowledge is the most common RAG source. It is rich but inconsistent and cannot be retrieved reliably without processing. The key is to convert it into standardized text while retaining necessary structure and metadata for chunking, embedding, and indexing. A PDF manual, for example, should preserve heading levels, page numbers, and table headers where possible. Otherwise, even a successful match is difficult to cite.

#### Preprocessing: Parsing and Cleaning

Parsing converts a source into processable text. Plain text and Markdown are relatively easy. PDF, Word, and web pages require recognition of headings, paragraphs, lists, and tables. Scans and screenshots require OCR. Preserve headings, page numbers, and section numbers wherever possible for retrieval and citation.

Cleaning removes retrieval noise rather than polishing the prose. Typical noise includes repeated headers and footers, garbled text, advertising, irrelevant navigation, and duplicate paragraphs. For tables, retain the relationship between headers and cells so values do not lose their field meanings.

Store body text with metadata after preprocessing. Metadata may include file name, source address, heading hierarchy, page, update time, and access permissions. It supports filtering, source display, and diagnosis.

#### Knowledge Chunking

An LLM cannot read the entire knowledge base on every request, and retrieval needs smaller units to index. Chunking is therefore central to RAG. Chunks that are too short lose context, while chunks that are too long mix topics. Both reduce accuracy.

The goal is not maximum length but a relatively clear topic with enough context. A retrieved chunk should contain relevant material rather than a large mixture. Four common approaches are:

**Structure-based chunking.** Split by heading, section, clause, question-answer pair, or paragraph. This suits clearly structured documents.

**Length-based chunking.** When structure is weak, split at a fixed character or token count with a small overlap.

**Recursive chunking.** Split first at natural boundaries such as sections and paragraphs, then divide chunks that remain too long.

**Semantic chunking.** Split at topic changes so each chunk represents a coherent semantic unit.

<a id="tab-chunking-strategies"></a>

*Table 3-3. Comparison of common text chunking strategies*

| **Strategy** | **Suitable Material** | **Advantage** | **Risk** |
| --- | --- | --- | --- |
| Heading or section | Structured manuals, policies, and terms. | Preserves document logic and supports citation. | A large section may remain too long. |
| Question-answer pair | FAQs and knowledge-base Q&A. | Naturally keeps questions with answers. | Coverage is limited by phrasing. |
| Fixed length | Long text without clear structure. | Simple and easy to process in batches. | May break semantic units. |
| Recursive | Documents with unstable hierarchy. | Balances size and natural boundaries. | Poor settings still make chunks too fine or coarse. |
| Semantic | Long documents with clear topic changes. | Good semantic consistency within chunks. | More computation and potentially unstable results. |

Table [3-3](#tab-chunking-strategies) compares these strategies. A practical starting point is structure first and length as a fallback. Split by headings, sections, or Q&A pairs, divide overly long chunks by length, and add a small overlap when answers frequently cross boundaries. Retain headings, source positions, and update times.

Test chunk quality with actual questions. Frequent retrieval of topically similar chunks that cannot answer the question suggests chunks are too large. Frequent omissions suggest they are too small or lack required context.

#### Vector Representation and Indexing

After chunking, the system needs a searchable representation for each chunk. A vector representation, commonly called an embedding, converts text to numbers so semantically similar text is closer in vector space. A user question can be embedded and compared with chunk vectors.

Vector retrieval can be understood as searching by meaning. “How do I reset my password?” and “If you forget your login credentials, reset them on the account security page” use different words but express related meanings.

An index usually stores the chunk, its vector, and metadata such as document name, section, page, version, update time, and permissions for source tracing and citation.

Unstructured knowledge has now moved from raw documents to a vector index. A vector store does not replace all other storage. Graph databases suit entity relationships, while relational databases suit structured data. Different questions require different retrieval paths.

### Building Semi-Structured Knowledge

Semi-structured knowledge has hierarchy, labels, or relationships without the rigidity of relational tables. Typical forms include knowledge graphs, FAQs, ticket records, and relationships extracted from documents. Its focus is not a passage of text but relationships among objects.

Graph data suits multi-hop queries and relationship tracing. A single text chunk may not fully answer which modules a feature depends on and which processes it affects. A graph can traverse dependency, impact, and containment relationships.

#### Preprocessing

For graph data, begin by defining scope: entity types, relationship types, attributes, and sources. An overly broad graph is hard to maintain, while an overly narrow one limits queries.

Preprocessing also includes entity normalization and disambiguation. One object may have abbreviations, aliases, and former names. Without normalization, it becomes duplicate nodes. Time-sensitive relationships should record effective dates and sources.

#### Information Extraction

Information extraction identifies entities, relationships, and events in documents. Entities may be systems, modules, people, organizations, concepts, or process nodes. Relationships may include contains, depends on, belongs to, responsible for, precedes, follows, and cites. Results often form triples such as “Module A depends on Module B.”

Rules, models, and human review can work together. Extraction makes implicit relationships explicit so retrieval can follow relationships as well as find text.

#### Graph Indexing

A graph index helps the system quickly find entities, relationships, and neighboring nodes. Unlike a vector index, it emphasizes connectivity and expands from one entity to related concepts, dependencies, or documents.

In RAG, graph data usually contributes to retrieval augmentation. The system identifies an entry entity, expands along relationships, and organizes the resulting nodes and documents for the LLM. Graphs do not replace text chunks; they organize relevant text within the correct relational scope.

### Building Structured Knowledge

Structured knowledge is organized into fields, rows, columns, primary keys, and foreign keys, as in spreadsheets, relational databases, and warehouse tables. Its value lies in field relationships and computability rather than textual similarity. Status queries, counts, filters, and time aggregations usually belong in databases. To count records added this month, query date and type fields instead of searching documents for similar wording.

#### Preprocessing

First define the meaning of tables and fields: what each table represents, what each field means, and how tables relate. Table and column names alone are often insufficient because real databases contain abbreviations, historical names, and internal terminology.

Next address quality and permissions. Nulls, duplicates, outliers, and inconsistent encodings affect results. Sensitive and internal fields and high-risk queries require masking and access control.

#### Normalization

Normalization keeps structured data clear, consistent, and queryable. Preserve fields, types, keys, time ranges, and business meanings instead of cutting records into ordinary text chunks.

It also maps business terms to database fields. Real systems usually maintain schemas, field explanations, synonyms, and example queries to connect natural-language questions with database structure.

#### Relational Database Access

A RAG system need not create a new relational database. More often, it accesses an existing database or data service through a safe interface. It first determines whether structured data is required, then generates a query using schemas, field explanations, and permission rules, and organizes the result for the LLM.

This is commonly called Text2SQL or NL2SQL. Correct syntax is not enough. The query must also be semantically correct, permission-compliant, and explainable.

## Knowledge Retrieval Methods

<a id="sec-ch3-knowledge-retrieval"></a>

Once the offline knowledge base is ready, the system must retrieve the right material. RAG quality depends heavily on retrieval. Even a strong model cannot reliably generate from irrelevant, incomplete, or untrustworthy evidence. Figure [3-3](#fig-retrieval-techs) frames this section: constructing a query, keyword, vector, graph, and SQL retrieval, followed by hybrid retrieval and reranking.

<a id="fig-retrieval-techs"></a>

![Knowledge retrieval methods](./imgs/retrieval_tech.png)

*Figure 3-3. Knowledge retrieval methods*

### Query Construction

Retrieval is more than sending a user's exact words to a database. Questions may be conversational, context-dependent, or multi-intent. Query construction turns them into requests appropriate to different stores. If a user asks, “What changed from the previous version?”, the system must resolve which rule is meant and decide whether to retrieve release notes, policy text, or a structured update field.

A reliable process has three steps. Intent recognition determines whether to search text, relationships, tables, or several sources. Query rewriting makes conversational language closer to source terminology while retaining the original question to avoid distortion. Constraint enrichment adds time ranges, document types, versions, permission scope, and entity names. Metadata constraints are often more reliable than text similarity alone.

Complex questions can be decomposed. “Who does this policy apply to, what is the approval process, and when does it take effect?” can become three searches whose results are merged. This improves recall. As query construction becomes more complex, preserve intermediate results so failures can be traced to interpretation, rewriting, or missing knowledge.

### Keyword Retrieval

Keyword retrieval ranks lexical matches using an inverted index. The system records which documents or fields contain each term, then scores queries from frequency, rarity, and field weights. TF-IDF and BM25 are common methods. BM25 is a classic ranking method based on probabilistic retrieval<sup>[2](#ref-robertson2009bm25)</sup>.

Keyword retrieval excels at exact matches such as identifiers, terms, names, organizations, models, titles, and versions. It is fast, explainable, and easy to combine with filters. Good retrieval uses metadata such as title, section, source, time, and document type as well as body text. An identifier match in a title is often more important than one in the body.

Its weakness is synonyms and implicit meaning. “How long will it take?” may fail to match a source that says “processing time limit.” Systems commonly use ElasticSearch[^1] or OpenSearch[^2] with tokenization, synonym dictionaries, field weights, and filters.

### Vector Retrieval

Vector retrieval embeds questions and chunks, then measures similarity using cosine similarity, inner product, or Euclidean distance. It handles synonyms, conversational questions, and conceptually related expressions better than keyword retrieval. “I cannot access my account” can match “steps for handling login failure” despite different wording.

It is mainly used for unstructured text and explanatory text in semi-structured knowledge. Accuracy requires sensible chunks, an embedding model suited to the language and domain, and metadata filters. A larger Top K is not always better. Too few results may miss evidence; too many introduce related but unhelpful material.

Vector stores commonly use approximate nearest-neighbor search for efficiency. Milvus[^3] and FAISS[^4] are representative tools. Beginners should focus on how query and chunk vectors are compared and why similarity does not necessarily mean answerability.

### Graph Retrieval

Graph retrieval targets semi-structured knowledge and questions involving entities, relationships, and paths. Rather than asking which passage is similar, it asks which entities are connected and how. For “Which components make up this device, and where are their maintenance requirements?”, the system can identify the device, then follow contains, maintenance requirement, and applicable document relationships.

Accuracy depends on entity recognition and relationship modeling. The system links names in the question to normalized graph entities, then expands one or more hops by relationship type. Queries may use Cypher, SPARQL, or graph statements generated with LLM assistance. Neo4j[^5] and NebulaGraph[^6] are representative tools.

Graphs clearly express relationships, hierarchy, dependencies, and impact. They are expensive to build, and weak entity or relationship extraction produces poor results. Systems often combine graphs with vector retrieval: the graph narrows entities and relationships, while text chunks provide citable explanations.

### SQL Retrieval

SQL retrieval serves structured questions about counts, status, time, ranking, detail lists, and aggregates. A current record status should come from a live database field rather than a similar sentence in a document. Text2SQL or NL2SQL converts a natural-language question into a database query.

Reliable SQL retrieval requires schema understanding: available tables, field meanings, relationships, and permitted fields. It must align business language such as “owner” with a field such as `owner_id` or `assignee`, then validate the query to prevent unauthorized, inefficient, or semantically incorrect SQL.

Real systems should not give a model unrestricted database access. They use read-only interfaces, field allowlists, permission filters, and masked results. High-risk queries can produce a plan or SQL draft for rule validation or human confirmation before execution.

### Reranking

Each retriever solves a different problem. Keywords find exact matches, vectors provide semantic recall, graphs traverse relationships, and SQL queries structured data. Real systems often use hybrid retrieval, merge candidates from several retrievers, and combine ranks through weighted sums, rank fusion, or Reciprocal Rank Fusion (RRF).

Hybrid retrieval tries to find all relevant candidates; reranking places the most useful first. The first stage retrieves broadly for recall. The second uses finer rules or models to judge relevance. Methods include cross-encoder rerankers, LLM relevance scores, metadata rules, and maximal marginal relevance to reduce duplication.

Reranking should consider whether a source directly supports the answer, not only semantic similarity. A topically similar passage may lack the answer, while a slightly lower-scoring passage contains an explicit field, date, or conclusion. Good ranking combines relevance, authority, recency, completeness, and diversity. Only a few high-quality results then enter the prompt, reducing noise and attention dilution.

## Online Retrieval-Augmented Generation

The preceding sections prepared knowledge and retrieved material. This section connects them into one question-answer flow. In Figure [3-4](#fig-generation), the user question is interpreted and organized, sent through retrieval, and combined with relevant evidence for the LLM. A basic RAG flow receives the question, completes the query, retrieves and reranks knowledge, compresses evidence, constructs an augmented prompt, and generates an answer.

<a id="fig-generation"></a>

![Online retrieval-augmented generation](./imgs/generation.png)

*Figure 3-4. Online retrieval-augmented generation*

### From User Question to Retrieval Query

Query construction also supports the online flow. A conversational question may depend on earlier turns. If a user first asks who a policy applies to and then asks “When does it take effect?”, the second query must be completed as “When does this policy take effect?” RAG therefore still needs the multi-turn history from Chapter 2, now both to generate an answer and to form a retrieval query.

A simple system can retrieve using the original question. Later improvements can add completion, keyword extraction, and rewriting. A rewritten query is not always better and may distort intent, so retain both original and rewritten forms and compare their results.

### Adding Retrieved Results to the Prompt

After retrieval, the prompt usually contains four parts: role, answer rules, retrieved material, and user question. Unlike Chapter 2, knowledge is supplied dynamically on each question rather than fixed mainly in the system prompt.

Do not place every result in the prompt. In Figure [3-4](#fig-generation), summarization and prompt engineering control input quality. Summarization compresses repetition and secondary content. The prompt defines answer boundaries, evidence presentation, and refusal rules. Together they give the model enough relevant, clear, traceable evidence.

The following is a simplified augmented prompt template.

```text
系统消息：
你是知识问答助手。请只依据“检索资料”回答问题。
如果检索资料没有覆盖答案，请说明当前资料无法确认，并建议人工核实。
回答时先给出结论，再列出依据。不要编造未出现的事实、数字或承诺。

检索资料：
[资料1] 文档第 3 节：该规则自 2026 年 1 月 1 日起生效。
[资料2] FAQ：若用户询问规则生效时间，应以正式发布文件为准。

用户问题：
这个规则什么时候生效？
```

The key to this template is an explicit source boundary. The model may organize the language, but it must not present information absent from the retrieved material as fact. When sources conflict, the answer should disclose the conflict and recommend human confirmation rather than forcibly merging them.

### Generating Answers and Presenting Evidence

A RAG answer should show its evidence, not merely sound natural. A useful teaching-stage structure is direct answer, supporting passage, and necessary reminder. For example:

```text
该规则自 2026 年 1 月 1 日起生效。
依据是资料1中“该规则自 2026 年 1 月 1 日起生效”的说明。
需要注意，具体执行口径仍应以正式发布文件为准。
```

This structure gives users a quick conclusion, lets learners and developers verify that the answer came from a retrieved passage, and makes refusal more stable when the knowledge base is insufficient.

### Common RAG Failures and Error Analysis

Connecting sources does not automatically make RAG reliable. Understanding failures is more important than examining successful examples alone. Common errors fall into three categories.

**Knowledge construction problems.** The knowledge base lacks relevant material, or parsing, chunking, and cleaning omit or misalign it. Correct retrieval cannot return evidence that is not available.

**Retrieval problems.** The answer exists, but unsuitable chunks, keywords, embeddings, or filters prevent recall. Retrieval may also return topically related passages that do not answer the question.

**Generation hallucinations.** The model gives a confident claim when results are insufficient or conditional. It may also misread a correct source's conditions, exceptions, or time range.

Evaluate knowledge correctness, retrieval hits, and source-grounded generation separately. A beginner project need not implement a sophisticated evaluation framework, but it should cultivate this decomposition.

## Hands-On Practice: Build a Knowledge-Augmented RAG Digital Employee

This project extends Chapter 2's configurable ChatBot with a knowledge base, retrieval debugging, and source display. The scenario remains insurance consultation. The objective is direct: retrieve relevant material, answer from it, and leave citations that users can inspect.

Beginners do not need to master complex backend engineering. Follow the basic chain: organize business documents into chunks, retrieve relevant chunks for a question, place them in a prompt, and display citations with the answer.

This practical sequence corresponds to the theory. Document preparation covers source boundaries, cleaning, chunking, and indexing. Question retrieval compares keyword, vector, and hybrid retrieval and the effect of `top_k`. Answer generation corresponds to the online RAG flow. When analyzing results, identify whether an error originated in the knowledge base, retrieval, or generation.

### Step 1: Start the System and Prepare a Business Document

Enter the code directory, install dependencies, and start the service.

```bash
cd {本章项目代码目录}
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. The system creates a local SQLite database and seeds a demonstration model, digital employee, knowledge tags, and insurance documents. The sidebar contains Chat, Knowledge Base, Model Configuration, and Digital Employees. This section focuses on the knowledge base, employees, and chat. Under Model Configuration, enter an OpenAI-compatible endpoint, model name, and API key. RAG conversations can call the LLM only after the model test succeeds.

To experience vector retrieval, configure an embedding model in the code directory. The project can operate without one by using keyword retrieval. This lets learners first understand the complete RAG chain and then compare keyword and vector retrieval.

Use insurance documents under `data/` or create your own through the web interface. Markdown and plain text are recommended at first because headings, paragraphs, and chunks remain visible. The material need not be long but should clearly cover an introduction, intended audience, coverage, waiting period, claim materials, and exclusions.

Suggested format:

```text
# 产品基础信息
产品名称：示例健康保障计划
适用人群：18 至 55 周岁，具体以投保规则为准。

# 等待期
本产品疾病责任等待期为 90 天。等待期内发生的疾病相关申请，应以合同条款为准。

# 理赔材料
常见材料包括身份证明、保单信息、医疗票据、诊断证明和保险公司要求的其他材料。

# 未覆盖事项
本文档不包含具体费率、收益承诺和最终理赔结论。
```

The explicit exclusions help learners observe how the system should handle missing rates, promised returns, and claim conclusions: state that they cannot be confirmed rather than inventing a complete answer. Real projects also store name, source, version, tags, and validity. These fields constrain retrieval and support traceability.

### Step 2: Build the Offline Knowledge Base

After a document is created or uploaded under Knowledge Base, the system builds its index by cleaning text, chunking it, generating vectors or a keyword index, and saving chunks with provenance. Think of this as dividing one document into information cards whose body and source are retained for retrieval.

```python
text = clean_text(document.content)
chunks = split_text(text, strategy="structure")
vectors = embed_texts([chunk.content for chunk in chunks])
save_chunks(document, chunks, vectors)
```

The excerpt shows the essential logic. Text is cleaned, divided primarily by Markdown headings and paragraphs, embedded for semantic retrieval, and saved with its sources. Vectors alone are insufficient because the model needs the original text and users need source titles.

The default strategy prioritizes structure and uses length as a fallback. Structure tends to preserve the meaning of terms, manuals, and FAQs and supports citation. Fixed-length chunks are easy to implement but may separate a waiting-period rule from its warning. Edit the same document and observe changes in chunk counts and results.

The chunk count and indexed status are the main observations. The former shows how many retrieval units were created; the latter shows whether they can participate in retrieval. Saved content with a failed index may be unavailable in online Q&A.

Figure [3-5](#fig-rag-practice-knowledge-list) shows the knowledge-base page after startup. Inspect document names, tags, chunk counts, index status, and validity. This is the output of offline construction.

Tags and validity implement source boundaries. A knowledge base must identify which sources belong to a business category, remain current, and may be retrieved by an employee. Clear boundaries reduce irrelevant prompt content and the risk of obsolete answers.

<a id="fig-rag-practice-knowledge-list"></a>

![Knowledge-base document list in the companion system](./imgs/rag_practice_knowledge_list.png)

*Figure 3-5. Knowledge-base document list in the companion system*

This step directly reflects knowledge sources and boundaries. A teaching document may be short, but its boundary must be explicit. Waiting periods and claim materials may be answered, while specific premiums and promised returns remain outside the current material. Only then can you determine whether RAG is grounded in sources rather than presenting general knowledge as a definite conclusion.

### Step 3: Debug Retrieval

Before testing chat, click Retrieval Debugging under Knowledge Base. Enter a question, select tags, retriever type, and `top_k`, and inspect whether the passages can answer it. “How long is the disease waiting period?” should retrieve the passage containing 90 days.

Figure [3-6](#fig-rag-practice-search-debug) shows a result with the source title, document, embedding model, score, and original passage. Inspect these passages before judging the final answer. Fluency alone is not evidence of quality.

<a id="fig-rag-practice-search-debug"></a>

![Checking a waiting-period result with retrieval debugging](./imgs/rag_practice_search_debug.png)

*Figure 3-6. Checking a waiting-period result with retrieval debugging*

Retrieval first narrows material by tags and validity, then ranks it with the selected retriever. If vector search is unavailable, keyword search is the fallback. The excerpt retains only strategy selection.

```python
chunks = load_chunks(tag_ids)
if retriever_type == "keyword":
    passages = keyword_search(query, chunks, top_k)
elif retriever_type == "vector":
    passages = vector_search(query, chunks, top_k)
else:
    passages = hybrid_search(query, chunks, top_k)
```

Keywords suit product names, clauses, identifiers, and explicit terms. Vectors suit questions whose wording differs but meaning is similar. Hybrid retrieval uses both. Beginners need not begin with complex algorithms; they should explain why different questions favor different methods.

Similarity does not equal answerability. A high-scoring passage may share the topic without providing the answer. A passage titled “Coverage and Waiting Period Details” cannot support a precise waiting period if it contains no number. Check the document, heading, and actual information required to answer.

### Step 4: Publish a RAG Digital Employee

Chapter 2 configured a role, objective, business information, constraints, and output. With RAG, lengthy business information is replaced by dynamically bound knowledge tags. The prompt defines how to answer; the knowledge base supplies what to answer from.

```python
rag_agent_config = {
    "role": "你是保险咨询数字员工。",
    "service_goal": "依据知识库资料回答保险咨询问题。",
    "knowledge_tag_ids": [2],
    "retrieval_top_k": 3,
    "retriever_type": "vector",
    "constraints": "只依据检索资料回答，资料不足时说明无法确认。",
    "output_instruction": "先给结论，再列依据，最后给出必要提醒。",
}
```

`knowledge_tag_ids` controls accessible sources, `retrieval_top_k` controls the number of chunks, and `retriever_type` selects retrieval. Begin with `top_k=3`, then compare 1 and 5 for omissions or noise.

Figure [3-7](#fig-rag-practice-agent-config) shows the configuration. The type is RAG, knowledge tags define retrieval scope, and chunk count and retriever type replace a large block of business background in the prompt.

This illustrates the ChatBot–RAG distinction. A basic ChatBot keeps small, stable material in the prompt. A RAG employee keeps business facts in the knowledge base and retains only the role, objective, constraints, and output format in the prompt. Product updates then primarily change the knowledge base.

<a id="fig-rag-practice-agent-config"></a>

![Knowledge tags and retrieval settings for a RAG digital employee](./imgs/rag_practice_agent_config.png)

*Figure 3-7. Knowledge tags and retrieval settings for a RAG digital employee*

### Step 5: Complete a RAG Conversation

A RAG conversation has four core steps: build a retrieval query, retrieve chunks, construct an augmented prompt, and generate and save the answer. In plain language: ask, look up sources, ask the model with those sources, and display both answer and evidence.

```python
query = build_query(user_input, chat_history)
passages = search_knowledge(query, agent_config)
prompt = build_rag_prompt(agent_config, passages, user_input)
answer = llm_generate(prompt)
save_answer_with_sources(answer, passages)
```

`passages` is the core of this flow. No passages means no external evidence. Inaccurate passages can ground an inaccurate answer. Debugging must inspect both retrieval and final generation.

The project numbers retrieved chunks as Source 1, Source 2, and Source 3 and explicitly instructs the model to answer only from them rather than hard-coding insurance material into the system prompt. A simplified template is:

```text
你是保险咨询数字员工。
请只依据下面的检索资料回答问题。
如果资料没有覆盖答案，请说明当前资料无法确认。

检索资料：
[资料1] 等待期：本产品疾病责任等待期为 90 天。
[资料2] 未覆盖事项：本文档不包含具体费率和收益承诺。

用户问题：
疾病责任等待期是多久？
```

The format is less important than the boundary. The model may compose language but may not state absent information as fact. Sources are saved with the answer and remain visible after a refresh. To review reliability, first ask whether the citations support the answer.

Figure [3-8](#fig-rag-practice-chat-sources) shows expanded sources on the Chat page. Inspect answer accuracy and whether the sources actually support it. A plausible answer with unsupported citations should be recorded as a retrieval or generation problem.

<a id="fig-rag-practice-chat-sources"></a>

![Sources displayed on the RAG conversation page](./imgs/rag_practice_chat_sources.png)

*Figure 3-8. Sources displayed on the RAG conversation page*

The practice maps to Figure [3-1](#fig-rag): knowledge construction on the left is offline; questions, retrieval, augmented prompts, and answers on the right are online. Understanding their division is central to RAG.

Connect results to the three failure types. If debugging misses the correct passage, the problem lies in knowledge construction or retrieval. If the passage is correct but the answer omits a condition, generation is at fault. If the knowledge base lacks an answer but the model remains certain, refusal constraints failed. This identifies which system stage needs improvement instead of merely saying that the model was wrong.

### Practice Tasks

1. Run the system, confirm that Knowledge Base contains at least one document, and inspect its chunks, tags, and status.
1. Create an 800–1,500 Chinese-character or roughly 500–900 English-word business document for one product or service, covering an introduction, rules, procedures, and common questions.
1. Debug at least three questions and record the document, source heading, passage, and score. Include a direct match, a conversational question, and a question absent from the sources.
1. Publish a RAG digital employee, bind the tags, initially set `top_k` to 3, and select Vector. Use Keyword if embedding is unavailable.
1. Complete a conversation and verify that sources appear below the answer. Refresh and confirm that historical sources remain.
1. Change `top_k` or the retriever and compare answers. Determine whether changes come from source content, chunking, retrieval, or model interpretation.

### Expected Outcomes

Submit a RAG practice report covering source material, sample chunks, retrieval debugging screenshots, employee configuration, test questions, answers, and error analysis. Include at least two failures and identify whether each originated in source content, chunking, retrieval, or generation. Explain the capability boundary: RAG helps a digital employee answer from external material, but reliable operation still requires reviewed sources, retrieval evaluation, and human confirmation.

## Assignments and Questions

1. Explain in your own words why RAG reduces fabrication risk without eliminating errors.
1. Compare keyword and vector retrieval, and give one suitable sales or customer-service question for each.
1. Select a business document, design two chunking schemes, and explain which fits better.
1. Design a response strategy for questions absent from the knowledge base, including refusal wording and human escalation.
1. Explain how a real enterprise should update, review, and retire sales or customer-service knowledge.

## References

1. <a id="ref-lewis2020rag"></a>Patrick Lewis, Ethan Perez, Aleksandra Piktus, Fabio Petroni, Vladimir Karpukhin, Naman Goyal, et al. [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401). Advances in Neural Information Processing Systems. 33, 9459–9474, 2020.

2. <a id="ref-robertson2009bm25"></a>Stephen Robertson, Hugo Zaragoza. The Probabilistic Relevance Framework: BM25 and Beyond. Foundations and Trends in Information Retrieval. 3, 4, 333–389, 2009. [DOI](https://doi.org/10.1561/1500000019).

[^1]: https://www.elastic.co
[^2]: https://opensearch.org/
[^3]: https://github.com/milvus-io/milvus
[^4]: https://github.com/facebookresearch/faiss
[^5]: https://neo4j.com/
[^6]: https://www.nebula-graph.io/

---

[← Previous Chapter](../chapter2_chatbot/README-en.md) | [Back to Contents](../README-en.md) | [Next Chapter →](../chapter4_agent_memory_tools/README-en.md)
