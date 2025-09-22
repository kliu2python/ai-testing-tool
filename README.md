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
        "reports_folder": "./reports"
      }'
```

The response returns the aggregated summary along with the path to the generated
`summary.json` report inside the reports directory.

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


## Acknowledgements

1. https://github.com/Nikhil-Kulkarni/qa-gpt
2. https://github.com/quinny1187/GridGPT
3. https://github.com/nickandbro/chatGPT_Vision_To_Coords
4. https://arxiv.org/abs/2304.07061
