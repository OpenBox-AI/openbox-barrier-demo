# OpenBox Barrier Demo

A local web demo showing how OpenBox-enforced barriers govern document access
for three fixed LangGraph agents: Amy, Barry, and Colin.

The dashboard lets you start each workflow, watch metadata searches and governed
document reads, and then observe Amy and Barry file the finished report to every
configured client folder through governed upload attempts. The application has
no client-access matrix and does not make authorization decisions itself.

## Configured research scenarios

| Agent | Assignment | Intended allowed sources | Intended blocked sources |
| --- | --- | --- | --- |
| Amy | Coca-Cola integration-risk briefing | Coca-Cola, Bank of America | Pepsi |
| Barry | Pepsi integration-risk briefing | Pepsi, Citi | Coca-Cola |
| Colin | Cross-industry change benchmark | Coca-Cola, Pepsi | Citi, Bank of America |

After writing its report, both Amy and Barry attempt the same ordered client-folder
sweep: Coca-Cola (`0001/10001`), PepsiCo (`0001/20001`), Bank of America
(`0001/30001`), and Citi Bank (`0001/30002`). Each row starts without an expected
verdict; the dashboard shows the complete OpenBox evaluate response returned for that
authenticated agent. Colin does not file because his report is cross-client and has no
unambiguous client filing purpose.

The research table describes the intended read scenarios, not application conditions.
Configure identity and document-access rules in OpenBox before running the demo.

## Three test use cases

1. **Amy — Barriers plus an OpenBox filing rule.** Keep barriers enabled for
   `read_document` and `upload_document`. Add an OpenBox Policy Rule that allows Amy
   to upload her finished report only to the Coca-Cola directory (`0001/10001`) and
   blocks uploads to every other client directory.
2. **Barry — Barriers only for reads and uploads.** Do not add Amy's destination-specific
   OpenBox Policy Rule to Barry. Let barriers determine the result of both
   `read_document` and `upload_document` activities.
3. **Colin — Barriers only for reads.** Colin's workflow uses barriers for `read_document`.
   It has no filing phase and never calls `upload_document`.

For Amy, both checks apply: a filing proceeds only when the OpenBox Policy Rule and
barriers allow it. A `BLOCK` from either check prevents the file from being written.

## How it works

```text
metadata search -> governed read -> returned evidence
                -> synthesis -> governed report write
                -> governed upload for each configured client folder
```

- Each agent runs in a separate process with its own OpenBox identity and credentials.
- The model cannot select an identity, credential, `userId`, or alternate read path.
- Document content enters the workflow only after a successful governed read.
- `upload_document(destination_document_id)` can name only a destination. Its source
  is bound internally to the current agent's staged report; identity, source path,
  and destination sequence are not model arguments.
- An ordinary OpenBox `BLOCK` on any filing attempt is recorded and the client-folder
  sweep continues without inspecting a provider-specific reason or metadata flag. The
  dashboard displays the complete evaluate response for each attempt.
- `HALT`, approval failures, API failures, invalid destinations, and other operational
  errors retain the SDK's normal terminal behavior.
- Blocked content and policy reasons never enter the model prompt.
- A blocked source is not retried through another agent or path.
- OpenBox failures stop the governed operation with `on_api_error="fail_closed"`.

The repository intentionally ships without an authorization policy. OpenBox is the
source of truth for every allow or block decision.

This is a **barriers and filing-entitlement demo**, not complete semantic mis-filing
prevention. It proves whether the authenticated agent may access the destination
client/matter folder. A future semantic demo would add a destination that barriers
allow but an independent active-scope Policy Rule rejects.

## Bundled documents

The demo includes four fictional documents:

```text
documents/0001/
├── 10001/Coca_Cola_MA.docx
├── 20001/Pepsi_Co_MA.docx
├── 30001/Bank_of_America_CEO.docx
└── 30002/Citi_Bank_Reorg.docx
```

The document library supports `.md`, `.txt`, and `.docx`. Metadata search uses file
names and relative paths without reading document bodies.

## Requirements

- Python 3.11+
- `uv`
- Node.js 22.13+ and `npm`
- A reachable OpenBox Core instance
- Three configured OpenBox agents
- An OpenAI API key

## 1. Install

```bash
git clone git@github.com:OpenBox-AI/openbox-barrier-demo.git
cd openbox-barrier-demo
uv sync --locked
cp .env.example .env
cd web
npm install
cd ..
```

The SDKs are installed from PyPI using `uv.lock`. The locked releases include
IAM v3 workload identity support.

## 2. Configure the agents

Open `.env` and provide:

- `OPENBOX_API_URL` and `OPENAI_API_KEY`;
- Amy's OpenBox agent name, API key, and workload private key under `AMY_OPENBOX_*`;
- Barry's OpenBox agent name, API key, and workload private key under `BARRY_OPENBOX_*`;
- Colin's OpenBox agent name, API key, and workload private key under `COLIN_OPENBOX_*`.

Each `*_OPENBOX_AGENT_NAME` must exactly match its agent in OpenBox. For IAM v3,
provide that agent's PKCS8 PEM RSA workload key as contents, not a file path:

```dotenv
AMY_OPENBOX_WORKLOAD_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nREPLACE_WITH_KEY_CONTENT\n-----END PRIVATE KEY-----"
```

The quoted `\n` escapes become real newlines when `.env` is loaded. Each worker uses
only its agent's prefixed credentials and ignores shared SDK signing variables.
For legacy DID signing, leave the workload key blank and set both
`*_OPENBOX_AGENT_DID` and `*_OPENBOX_AGENT_PRIVATE_KEY`. With all signing fields
unset, the SDK uses API-key-only authentication; Core must permit that mode for the
configured agent. Never commit `.env`, API keys, or private keys.

The default document directory is `./documents`, staged reports are written to
`./output`, and successful filings are copied to the separate
`./filed_documents/{matter}/{client}/{filename}` tree. Filed reports are not part
of future research searches.

## 3. Configure barriers

Configure and activate the policies required by the three test use cases. Add the
Coca-Cola-only upload rule to Amy, but do not add that destination-specific rule to
Barry or Colin. Baseline OpenBox Policy Rules should otherwise allow the governed
activities so barriers can determine the remaining access results.

The demo sends every tool call through OpenBox using the active agent's fixed identity;
it does not contain fallback authorization logic or predicted upload verdicts.

If the observed results are surprising, check the deployed policy and agent identity
mapping rather than adding access conditions to this application.

## 4. Start the web demo

From the project root, run:

```bash
uv run barrier-web
```

This single command starts both the Python workflow API and the Vinext dashboard.
The launcher prints the exact dashboard URL, normally `http://localhost:3000`. If a
default port is busy, it selects a nearby free port and prints the updated URL.

Do not run only `npm run dev`; the dashboard also needs the Python workflow API.

## 5. Run the workflows

1. Open the dashboard URL printed by the launcher.
2. Confirm the header shows **Live API connected**.
3. Click **Start workflow** on Amy, Barry, or Colin.
4. Start the other agents when you want to compare their policy outcomes.
5. Watch Amy and Barry move through Search, Read, Synthesize, Write, and File.
   Colin retains the four-step research workflow.

The dashboard shows:

- the configured document tree;
- live workflow progress and events;
- allowed, blocked, and failed document reads;
- sanitized OpenBox evaluate responses for operator visibility;
- final status and the generated briefing.
- every client-folder filing attempt in order, with a blocked/committed summary;
- a filed-reports tree that refreshes only after a successful upload.

A successful run may finish as **Completed** or **Completed with restrictions**.
Blocked documents remain unavailable to synthesis, while the workflow continues
with other research leads. Reports use only evidence returned by allowed reads. The
filing summary is calculated from the actual four OpenBox decisions, and no file is
written for a blocked destination.

## Stop the demo

Press `Ctrl+C` in the terminal that started the launcher. This stops both the API
and dashboard processes.

## Troubleshooting

| Problem | Check |
| --- | --- |
| Local API offline | Start the demo with `uv run barrier-web`, not only the frontend. |
| The browser cannot connect | Use the exact URL printed by the launcher; a default port may have been busy. |
| Changes are not visible | Stop and restart the launcher. The Python process does not reload automatically. |
| Every governed action fails | Verify `OPENBOX_API_URL`, agent names, credentials, and the active OpenBox policy. |
| Access differs from the configured scenario | Check the active barriers and identity mapping. |
| All uploads are blocked | Inspect the complete evaluate responses in the filing rows, then verify the active OpenBox Policy Rules, barriers, and identity mapping. |
