# AI Testing Tool

## Demo

The test case is

```
When you add a google account in Passwords & accounts, username is abc@gmail.com, password is 123456. Then you should see an error "Couldn't find your Google Account".
```

![](./ai-testing-tool-5x-demo.gif)

## Architecture

![](https://images.shangjiaming.top/QA%20POC_2024-05-03_14-13-58.png)
![](https://images.shangjiaming.top/ai-testing-tool-sequence-diagram.png)

## How to use it?

Run the following command to run the tool

```sh
OPENAI_API_KEY=<openai api key> python ai-testing-tool.py <system prompt file> <task file> \
  --server=<automation server address> --platform=<android|ios|web>
```

Run the following command to run the tool in debug mode

```sh
python ai-testing-tool.py <system prompt file> <task file> --debug \
  --server=<automation server address> --platform=<android|ios|web>
```

## Running as a FastAPI service

You can expose the tool as a remote service using FastAPI. Install the
requirements and launch the API with Uvicorn:

```sh
pip install -r requirements.txt
uvicorn ai_testing_tool.api:app --host 0.0.0.0 --port 8000
```

The server listens on all interfaces so that it can be reached from remote
clients. Trigger a run by sending a `POST` request to `/run` with the prompt,
tasks, and configuration:

```sh
curl -X POST "http://<server-ip>:8000/run" \
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

## Acknowledgements

1. https://github.com/Nikhil-Kulkarni/qa-gpt
2. https://github.com/quinny1187/GridGPT
3. https://github.com/nickandbro/chatGPT_Vision_To_Coords
4. https://arxiv.org/abs/2304.07061
