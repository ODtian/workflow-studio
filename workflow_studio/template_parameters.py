"""Expose GGUF chat-template parameters with their original values."""
from jinja2 import nodes


def template_options(params):
    options = {}
    if params.get("thinking", "auto") != "auto":
        options["enable_thinking"] = params["thinking"] == "on"
    if params.get("reasoning_effort", ""):
        options["reasoning_effort"] = params["reasoning_effort"]
    return options


def reasoning_field(llm=None):
    field = {"key": "reasoning_effort", "label": "推理强度 · reasoning_effort", "type": "text",
             "section": "生成", "default": "", "placeholder": "模型默认",
             "hint": "原值传入 GGUF 自带模板；选择随主模型保存。"}
    if llm is None:
        return field
    if getattr(llm, "_studio_mtp", False):
        template = llm.template._template_text
        environment = llm.template._template.environment
    else:
        from llama_cpp.llama_chat_format import Jinja2ChatFormatter
        template = llm.metadata.get("tokenizer.chat_template", "")
        environment = Jinja2ChatFormatter(template, eos_token="", bos_token="")._environment.environment
    tree = environment.parse(template)
    aliases = {"reasoning_effort"}
    default = ""
    for assignment in tree.find_all(nodes.Assign):
        names = {name.name for name in assignment.find_all(nodes.Name)}
        if isinstance(assignment.target, nodes.Name) and names & aliases:
            aliases.add(assignment.target.name)
    for expression in tree.find_all(nodes.Filter):
        names = {name.name for name in expression.find_all(nodes.Name)}
        if expression.name == "default" and names & aliases and expression.args and isinstance(expression.args[0], nodes.Const):
            default = expression.args[0].value
    for comparison in tree.find_all(nodes.Compare):
        if not isinstance(comparison.expr, nodes.Name) or comparison.expr.name not in aliases:
            continue
        for operand in comparison.ops:
            if operand.op in ("in", "notin") and isinstance(operand.expr, (nodes.Tuple, nodes.List)):
                values = [item.value for item in operand.expr.items if isinstance(item, nodes.Const)]
                if values and all(isinstance(value, str) for value in values):
                    field.update(type="select", options=[{"label": "模型默认" + ("（" + str(default) + "）" if default else ""), "value": ""}] +
                                 [{"label": value, "value": value} for value in values])
                    return field
    return field
