# AI Testing Tool

## Demo

The test case is

```
When you add a google account in Passwords & accounts, username is abc@gmail.com, password is 123456. Then you should see an error "Couldn't find your Google Account".
```


## Architecture

![](https://images.shangjiaming.top/QA%20POC_2024-05-03_14-13-58.png)
![](https://images.shangjiaming.top/ai-testing-tool-sequence-diagram.png)

## How to use it?

Run the following command to run the tool

```sh
OPENAI_API_KEY=<openai api key> python backend_server.py <system prompt file> <task file> \
  --server=<automation server address> --platform=<android|ios|web>
```

Run the following command to run the tool in debug mode

```sh
python backend_server.py <system prompt file> <task file> --debug \
  --server=<automation server address> --platform=<android|ios|web>
```

## Running as a FastAPI service

You can expose the tool as a remote service using FastAPI. Install the
requirements and launch the API with Uvicorn:

```sh
pip install -r requirements.txt
uvicorn backend_server.api:app --host 0.0.0.0 --port 8090
```

The server listens on all interfaces so that it can be reached from remote
clients. Trigger a run by sending a `POST` request to `/run` with the prompt,
tasks, and configuration:

```sh
curl -X POST "http://<server-ip>:8090/run" \
  -H "Content-Type: application/json" \
  -d '{
        "prompt": "<system prompt text>",
        "tasks": [ ... task definitions ... ],
        "server": "http://localhost:4723",
        "platform": "android",
        "targets": [
          {"name": "browser", "platform": "web", "server": "http://localhost:4444", "default": true},
          {"name": "phone", "platform": "android", "server": "http://localhost:4723"}
        ],
        "reports_folder": "./reports"
      }'
```

The response returns the aggregated summary along with the path to the generated
`summary.json` report inside the reports directory.

When you define one or more automation targets the runner no longer requires the
top-level `server` and `platform` fields — each target provides its own
configuration instead.

### Coordinating multi-platform flows

When a scenario requires two or more platforms to work together—such as approving
an MFA challenge on mobile after initiating a login on the web—you can define a
set of `targets`. Each target initialises its own driver session and is
referenced by its `name`.

Autonomous tasks can switch between targets by including a `target` field in the
action JSON returned by the LLM (or by providing it explicitly inside scripted
steps). If `target` is omitted the agent continues using the current context.
Targets may also be selected by specifying a `platform` hint in the action
payload.

Example action emitted by the agent:

```json
{
  "action": "tap",
  "target": "phone",
  "xpath": "//XCUIElementTypeButton[@name='Approve']"
}
```

The runner records the originating target with each step so that the generated
reports capture both sides of the interaction.

## LangChain multi-agent email-to-test workflow

The project now includes a LangChain-inspired multi-agent orchestration module that extracts issues from customer emails, triggers mobile automation agents to reproduce them, and feeds the findings back to customers or internal teams. The workflow coordinates three roles:

1. **Email Agent**: Connects to IMAP/SMTP or consumes raw emails provided in the request body, parses the customer description, and extracts the platform, version, and reproduction steps. When information is missing or a test fails, it composes a professional follow-up email.
2. **Mobile AI Test Agent**: Selects devices from the `mobile proxy` pool that match the requested platform and OS version, invokes the existing Appium runner to reproduce the issue, and archives the resulting report.
3. **QA Reporter Agent**: When tests succeed, a known issue is confirmed, public troubleshooting guidance is available, or human escalation is required, it generates a structured report for customer support and engineering teams.

Trigger the workflow through the new `/multi-agent/run` FastAPI endpoint:

```sh
curl -X POST "http://<server-ip>:8090/multi-agent/run" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
        "customer_email": "customer@example.com",
        "subject_keywords": ["crash", "login"],
        "devices": [
          {"name": "qa-iphone", "platform": "ios", "server": "http://proxy:4723", "os_version": "17"}
        ],
        "emails": [
          {
            "subject": "App crashes on login",
            "sender": "customer@example.com",
            "received_at": "2024-06-01T02:30:00Z",
            "body": "Open the app -> enter account -> tap log in and the app immediately exits. Device: iOS 17.4, App 5.2"
          }
        ]
      }'
```

In production you can switch to the `imap` configuration to provide mailbox credentials, allowing the system to pull matching emails directly from a live inbox. The response includes the workflow status (awaiting customer input, resolved, or escalated), copies of outbound emails, a summary of the automation results, and the report path so support or engineering can quickly follow up.

### Enabling HTTPS/TLS

The backend can serve traffic over HTTPS by providing certificate details through
environment variables when launching the API (either with `python
backend_server/api.py` or via Uvicorn directly):

```sh
APP_SSL_CERTFILE=/path/to/cert.pem \
APP_SSL_KEYFILE=/path/to/key.pem \
APP_SSL_CA_CERTS=/path/to/ca-bundle.pem \  # optional
APP_SSL_KEYFILE_PASSWORD=secret \          # optional
python -m backend_server.api
```

Both `APP_SSL_CERTFILE` and `APP_SSL_KEYFILE` must be supplied to enable TLS.
Optional `APP_SSL_CA_CERTS` and `APP_SSL_KEYFILE_PASSWORD` values are respected
when present. When these variables are set the server automatically exposes HTTPS
on the configured port.

## Integrating the multi-agent email workflow

The LangChain-inspired workflow ships with modular components so you can adopt it
incrementally. This section outlines how to connect a live mailbox, point the
mobile testing agent at your device farm, and tailor the QA reporter output for
your support tooling.

### Configuring IMAP and outbound email

The email agent can ingest messages in two ways:

1. **Direct payloads** – Include an `emails` array in the `/multi-agent/run`
   request body (as shown above). This is convenient for testing or when another
   service already retrieves messages.
2. **IMAP polling** – Provide mailbox credentials so the email agent can fetch
   unread conversations itself. Add an `imap` object to the request:

   ```json
   {
     "imap": {
       "host": "imap.gmail.com",
       "port": 993,
       "username": "support@example.com",
       "password": "<app-password>",
       "use_ssl": true,
       "folder": "INBOX",
       "search": ["UNSEEN", "SUBJECT \"crash\""]
     }
   }
   ```

   * `search` accepts an array of IMAP search terms (e.g., `FROM`, `SINCE`,
     `SUBJECT`). When omitted the agent retrieves all unread mail in the folder.
   * Use app passwords or OAuth-based IMAP tokens instead of primary account
     passwords whenever possible.

Outbound replies are sent via the same email agent. Configure SMTP credentials in
the `smtp` block to enable automated responses:

```json
{
  "smtp": {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": "support@example.com",
    "password": "<app-password>",
    "use_tls": true
  }
}
```

When SMTP settings are omitted the agent logs the drafted response without
sending it, making it safe to validate the workflow in staging.

### Designing a subscription portal

The workflow can operate in a subscription mode where support engineers register
their mailbox credentials, select keywords to watch for, and toggle which
automation features the platform should run. The portal flow looks like this:

1. **User registration** – Each user signs in via the existing `/auth/signup`
   and `/auth/login` endpoints to obtain a bearer token.
2. **Create a subscription** – Call `POST /subscriptions` with the IMAP host,
   username, password (or app password), optional SMTP override, and the list of
   subject keywords to match. You can also toggle the available automation
   features:
   - `auto_test`: launch the mobile automation agent to reproduce customer
     steps.
   - `request_additional_details`: allow the system to email the customer when
     information is missing.
   - `public_document_response`: send resolution emails that include known
     troubleshooting content.
   - `create_mantis_ticket`: generate a structured Mantis draft summarising the
     findings.
3. **Execute runs** – Invoke `POST /subscriptions/{id}/run` with the device
   pool configuration. The backend will pull the latest messages matching the
   stored keywords, execute the enabled functions, and return the outcome
   alongside any follow-up or resolution emails.
4. **Review drafts** – When the Mantis feature is enabled the response contains
   a machine-generated ticket draft (`mantis_ticket`) with a title, description,
   reproduction steps, and severity recommendation that can be pushed directly
   into your bug tracker.

Every time the orchestrator runs the backend stores a structured copy of the
workflow response. You can retrieve historic executions with `GET /workflows`
and pull aggregated status counts via `GET /dashboard/metrics`. Human reviewers
can submit 1–5 star feedback for any generated artefact (follow-up emails,
resolution emails, QA reports, or Mantis tickets) using `POST /ratings`. The
highest rated examples are automatically fed back into the email and reporting
prompts as style guidance so future responses adopt the tone and structure that
your team prefers.

All secrets are encrypted at rest using the `SUBSCRIPTION_SECRET_KEY`
environment variable. Generate a key with

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

and provide it when launching the API server. The same key must be reused across
deployments to decrypt stored passwords.

### Connecting the mobile proxy or device cloud

The mobile agent consumes a list of available devices from the `devices` array in
the `/multi-agent/run` payload. Each entry mirrors the target definition used by
the core runner:

```json
{
  "name": "qa-iphone",
  "platform": "ios",
  "server": "http://proxy:4723",
  "os_version": "17.4",
  "capabilities": {
    "wdaLocalPort": 8100,
    "bundleId": "com.example.app"
  }
}
```

* `os_version` is optional but allows the agent to match customer requests that
  specify platform versions. If no device satisfies the request, the email agent
  will ask the customer to clarify or offer alternatives.
* Extra `capabilities` are forwarded to Appium so you can declare custom device
  options or application identifiers.

When a device completes a run, the agent stores the report path inside the
workflow response and attaches it to the generated QA summary.

### Customising QA reports and downstream integrations

The QA reporter agent produces a structured payload with:

* An executive summary of the observed behaviour
* Detailed reproduction steps and test evidence links
* Suggested follow-up actions (e.g., request more info, escalate, close ticket)

You can post-process this payload to push results into your CRM or incident
management tooling. Two common patterns are:

* **Webhook forwarding** – After receiving the workflow response, send the report
  to an internal webhook that files tickets or updates status dashboards.
* **Knowledge base enrichment** – Store successful reproductions and resolutions
  in a searchable database so future issues can be triaged automatically.

The agent prompt strings live in `backend_server/agents/prompts.py`; adjust them
to match your organisation's tone or compliance requirements. Tests under
`backend_server/tests/test_multi_agent_workflow.py` confirm the orchestration
logic, and you can add scenario-specific fixtures to validate your custom flows.

## Web Frontend

A modern React and TypeScript frontend is available in the `frontend_server/` directory.
It uses [Vite](https://vitejs.dev/) and Material UI components to interact with the
FastAPI service.

### Running the frontend

```sh
cd frontend_server
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Then open [http://localhost:5173](http://localhost:5173) in your browser. The UI
lets you configure the API base URL (default `http://localhost:8090`), trigger
new automation runs, inspect queued tasks, and fetch results.

For production builds you can run:

```sh
npm run build
```

which outputs static assets in `frontend_server/dist/`. Use `npm run preview` to test the
production build locally.

## Running the full stack with Docker Compose

The repository now ships with a `docker-compose.yml` file that builds and launches
the FastAPI backend, Redis queue worker, Redis itself, and the production Nginx
frontend. The services share persistent volumes for the SQLite database and Redis
data. To start everything with the Docker CLI, run:

```sh
docker compose up --build
```

The command exposes the API at `https://localhost:8090` (if TLS certificates are
provided) and the frontend at `http://localhost:5173`. Environment variables such
as `BACKEND_LOG_LEVEL` can be supplied to adjust logging verbosity for the backend
and queue worker containers.


## Acknowledgements

1. https://github.com/Nikhil-Kulkarni/qa-gpt
2. https://github.com/quinny1187/GridGPT
3. https://github.com/nickandbro/chatGPT_Vision_To_Coords
4. https://arxiv.org/abs/2304.07061
