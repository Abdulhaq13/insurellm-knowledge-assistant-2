# AI Knowledge Assistant
### Instant, accurate answers from your company's own documents, with the source behind every answer.

> **Prepared by:** [Your Name / Company] · **Contact:** [email] · [phone] · [website]

---

## 1. The problem your team faces every day

Every organisation has its knowledge spread across contracts, policies, product manuals, HR files, reports and email attachments. As a result:

- **Time is lost searching.** Employees spend hours every week looking for information that already exists somewhere.
- **The same questions keep coming back.** Senior staff and support teams answer them again and again.
- **Answers are inconsistent.** Two people give two different answers to the same customer.
- **Onboarding is slow.** New hires take weeks to learn where everything is.
- **Knowledge walks out of the door.** When experienced people leave, what they knew goes with them.
- **Generic AI chatbots don't help.** Tools like ChatGPT don't know your private documents, and they confidently make up answers that sound correct.

---

## 2. The solution

The **AI Knowledge Assistant** is a private chat assistant trained on **your** documents. Your team asks questions in plain language and gets:

- ✅ **Accurate answers** drawn only from your approved documents
- ✅ **Sources for every answer**, so anyone can check the original in one click
- ✅ **An honest "I don't know"** when the answer isn't in your documents, never a guess
- ✅ **Conversation memory**, so follow-up questions like *"and what about his contract?"* just work
- ✅ **Answers in seconds**, 24/7

> **Example**
> **Q:** *"What is the renewal term in our contract with Belvedere Insurance?"*
> **A:** *"The contract renews automatically for 12-month terms unless either party gives 60 days' written notice."*
> 📄 *Source: Contracts / Belvedere Insurance – Section 4*

---

## 3. How it works (in plain terms)

```
 Your documents ──► 1. Read & organise ──► 2. Index for search ──► Secure knowledge base
                                                                          │
 Your question ──► 3. Understand the question ──► 4. Find the best passages ┘
                                                        │
                                  5. Write the answer from those passages only
                                                        │
                                   Answer + clickable sources ◄┘
```

1. **Read and organise.** We load your files (PDF, Word, web pages, Markdown and text) and split them into well-structured sections without breaking tables or headings.
2. **Index for search.** Each section is indexed in two ways: by **meaning**, so it can find *"staff leave policy"* when you type *"holiday rules"*, and by **exact keywords**, so it can find contract numbers, names and product codes.
3. **Understand the question.** Vague or follow-up questions are rewritten into precise searches, taking the conversation into account.
4. **Find the best passages.** A second, more precise ranking step picks the most relevant passages from dozens of candidates.
5. **Answer with evidence.** The AI writes the answer **only** from those passages and cites where each fact came from.

This approach is called **Retrieval-Augmented Generation (RAG)**. It is the industry-standard way to make AI accurate on private data.

---

## 4. Problems we solved and how

We built this system, tested it, and fixed the weaknesses that make typical document chatbots unreliable.

| Common problem with AI document tools | How our assistant handles it |
|---|---|
| **Makes up answers** | Answers come only from retrieved passages. If nothing relevant is found, it says so. |
| **Can't be checked** | Every answer shows its sources, so users can verify in one click. |
| **Misses exact names, IDs and numbers** | **Hybrid search** combines meaning-based search with exact keyword search. |
| **Picks the wrong passage** | A dedicated **re-ranking** step reorders the candidates by true relevance. |
| **Loses context mid-conversation** | Follow-up questions are rewritten using the chat history. |
| **Breaks tables and sections apart** | **Structure-aware splitting** keeps headings, sections and tables intact. |
| **Chunks lose their meaning out of context** | Each section is tagged with its document context, for example *"From the Belvedere contract, Section 4"*. |
| **Needs a full rebuild whenever a file changes** | **Incremental updates** re-process only files that are new or changed. |
| **Slows down or fails with lots of data** | A scalable vector database with filtering, batching and caching. |
| **Anyone can see everything** | **Access control** limits which documents each user or team can search. |
| **Quality is a guess** | A built-in **evaluation suite** measures accuracy, and results are shared with you. |

---

## 5. Where it helps: use cases

| Team | What they ask | Value |
|---|---|---|
| **Customer support** | "What does the premium plan cover?" | Faster, consistent replies and fewer escalations |
| **Sales** | "Which clients use product X, and on what terms?" | Instant product and contract knowledge on calls |
| **Legal and contracts** | "Which contracts auto-renew next quarter?" | Contract review in minutes, not days |
| **HR** | "How many leave days do new employees get?" | Self-service answers for staff |
| **Onboarding** | "Who owns the claims product?" | New hires productive in days |
| **Operations and compliance** | "What is our data-retention policy?" | The approved answer every time, with the source |
| **Management** | "Summarise our key client commitments." | Quick overview across many documents |

**Industries:** insurance, finance, legal firms, healthcare administration, real estate, education, IT services, manufacturing, and any document-heavy business.

---

## 6. Accuracy you can measure

We don't ask you to take accuracy on trust. For every client we:

1. **Build a test set** of real questions from your team, with the correct answers.
2. **Measure retrieval quality**: does the system find the right passage, and does it rank it near the top? We use the standard metrics MRR, nDCG and keyword coverage.
3. **Measure answer quality**: every answer is scored for **accuracy, completeness and relevance** against the correct answer.
4. **Share the scores** with you before go-live, and again after every major update.

---

## 7. Built to scale

| Stage | Data size | Setup |
|---|---|---|
| **Pilot** | Up to a few thousand documents | Single secure deployment, fast to launch |
| **Business** | Tens of thousands of documents | Scalable vector database, incremental sync, caching |
| **Enterprise** | Hundreds of thousands of documents or more | Distributed search, per-department filtering, multiple teams, monitoring |

- **Many formats:** PDF, DOCX, HTML, Markdown, TXT, with scanned documents via OCR on request
- **Auto-sync:** new and updated files are picked up without rebuilding everything
- **Filtering:** search within a department, document type, date range or client
- **Fast responses:** answers are shown as they are generated, and common questions are cached

---

## 8. Security and privacy

- 🔒 **Your data stays yours.** It is never used to train public AI models.
- 🔒 **Private deployment options:** our secure cloud, your own cloud account, or fully **on-premise** using open-source models for highly sensitive data.
- 🔒 **Access control:** users only get answers from documents they are allowed to see.
- 🔒 **Secrets and keys** are stored securely and never kept inside the application code.
- 🔒 **Audit logs** record questions and sources for compliance review (optional).
- 🔒 **Protection against manipulation:** safeguards against malicious instructions hidden inside documents.

---

## 9. Flexible AI models

We are **not locked to one AI provider**. Depending on your budget, privacy and accuracy needs, the assistant can run on:

- **Premium cloud models** for the highest answer quality
- **Low-cost fast models** for high-volume use
- **Open-source models** hosted privately or on-premise, with no data leaving your environment

Switching models is a configuration change, not a rebuild.

---

## 10. How we work with you

| Step | What happens | Typical timeline* |
|---|---|---|
| **1. Discovery call** | We learn your documents, users and key questions | Day 1 |
| **2. Pilot** | We load a sample of your documents and build a test set | ~1–2 weeks |
| **3. Accuracy review** | We share the measured scores and tune the system with you | ~1 week |
| **4. Launch** | Full document set, user access, team training | ~1–2 weeks |
| **5. Ongoing support** | Monitoring, updates, new documents, quality reports | Monthly |

\*Timelines depend on document volume and complexity.

---

## 11. Packages

| | **Starter** | **Business** | **Enterprise** |
|---|---|---|---|
| Documents | Up to [X] | Up to [Y] | Custom |
| Users | Up to [N] | Up to [M] | Unlimited |
| Web chat interface | ✅ | ✅ | ✅ |
| Source citations | ✅ | ✅ | ✅ |
| Hybrid search and re-ranking | ✅ | ✅ | ✅ |
| Accuracy report | Initial | Quarterly | Monthly |
| Auto-sync of new documents | — | ✅ | ✅ |
| Access control by team | — | ✅ | ✅ |
| Private / on-premise deployment | — | — | ✅ |
| Integrations (Slack, Teams, website widget, API) | — | Optional | ✅ |
| Support | Email | Priority | Dedicated |
| **Price** | [₹/$ setup + monthly] | [₹/$ setup + monthly] | Custom quote |

---

## 12. Frequently asked questions

**Will it make things up?**
It is designed to answer only from your documents and to say "I don't know" otherwise. Every answer shows its sources so users can verify it, and accuracy is measured before launch.

**Is our data safe?**
Yes. Your documents are stored privately, access can be restricted per user, and fully on-premise deployment is available.

**What if our documents change?**
New and updated files are synced automatically. There is no need to rebuild the system.

**Do we need technical staff?**
No. We handle setup, tuning and maintenance. Your team just asks questions.

**Can it connect to our existing tools?**
Yes. It can be offered as a web app, a website chat widget, a Slack or Microsoft Teams bot, or an API.

**Can we try it first?**
Yes. A live demo is available, and a pilot on a sample of your own documents is the recommended first step.

---

## 13. Next step

📅 **Book a free 30-minute demo.** We'll show the assistant answering questions, then discuss a pilot on your own documents.

**[Your Name]** · [email] · [phone] · [website / live demo link]

---
---

## Appendix (internal, remove before sending to clients): current status vs. roadmap

Only promise what is delivered. Status of each capability described above:

| Capability | Status |
|---|---|
| RAG chat with conversation memory and a sources panel | ✅ Built (`app.py`, `implementation/`) |
| Query rewriting, multi-query retrieval, LLM re-ranking | ✅ Built (`pro_implementation/`), needs a retry limit and rerank validation |
| Evaluation suite (MRR, nDCG, coverage, LLM judge) | ✅ Built. Fix the CLI crash in `evaluation/eval.py:186` |
| Free-model setup (Groq/Gemini with local embeddings) | 🔧 To do: current plan for development |
| `.gitignore`, secrets handling, pinned requirements | 🔧 To do: before any deployment |
| Relative source paths (hide local `D:\` paths) | 🔧 To do |
| Hugging Face Space deployment (README header, LFS or rebuild at startup) | 🔧 To do |
| Structure-aware chunking and contextual chunk headers | 🔧 To do |
| Hybrid search (BM25 + vector) and cross-encoder re-ranking | 🔧 To do |
| Clickable citations inside answers | 🔧 To do |
| PDF / DOCX / HTML loading, OCR | 🔧 To do |
| Incremental sync (file hashing) | 🔧 To do |
| Metadata filtering and access control | 🔧 To do |
| Scalable vector DB (Qdrant / pgvector), caching, async | 🔧 To do: needed for the Business/Enterprise tiers |
| Slack / Teams / widget / API integrations | 🔧 To do: offer only after building |
| Switch to OpenAI `text-embedding-3-small` | ⏳ Later, when the first client signs |
