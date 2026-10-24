"""Translate the GGUF template's Qwen XML/JSON tool calls into Pi calls."""
import json
import re
import uuid


def visible_text(text):
    return text.split("<tool_call>", 1)[0].rstrip()


def parse_calls(text, tools):
    schemas = {tool["function"]["name"]: tool["function"]["parameters"] for tool in tools}
    calls = []
    for body in re.findall(r"<tool_call>(.*?)</tool_call>", text, re.S):
        match = re.search(r"<function=([^>]+)>(.*?)</function>", body, re.S)
        if match:
            name, body = match.groups()
            props = schemas[name].get("properties", {})
            args = {}
            for key, value in re.findall(r"<parameter=([^>]+)>(.*?)</parameter>", body, re.S):
                value = value.strip("\n")
                args[key] = value if props.get(key, {}).get("type") == "string" else json.loads(value)
        else:
            call = json.loads(body)
            name, args = call["name"], call["arguments"]
        calls.append({"id":"call_" + uuid.uuid4().hex[:16], "name":name, "arguments":args})
    return calls
