"""Expose GGUF chat-template parameters with their original values."""
from jinja2 import Environment, nodes


def template_options(params):
    options = {}
    if params.get("thinking") in ("on", "off"):
        options["enable_thinking"] = params["thinking"] == "on"
    if params.get("reasoning_effort", ""):
        options["reasoning_effort"] = params["reasoning_effort"]
    return options


def _template_tree(template):
    return Environment(extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do']).parse(template)


def thinking_field(template=''):
    tree = _template_tree(template)
    supported = any(node.name == 'enable_thinking' for node in tree.find_all(nodes.Name))
    return {"key": "thinking", "label": "思考 · enable_thinking", "type": "select", "section": "生成",
            "default": "auto", "hidden": not supported,
            "options": [{"label": "模型默认", "value": "auto"},
                        {"label": "开启", "value": "on"}, {"label": "关闭", "value": "off"}]}


def reasoning_field(template=''):
    field = {"key": "reasoning_effort", "label": "推理强度 · reasoning_effort", "type": "text",
             "section": "生成", "default": "", "placeholder": "模型默认",
             "hint": "原值传入 GGUF 自带模板；选择随主模型保存。"}
    tree = _template_tree(template)
    field['hidden'] = not any(node.name == 'reasoning_effort' for node in tree.find_all(nodes.Name))
    aliases = {"reasoning_effort"}
    default = ""
    for assignment in tree.find_all(nodes.Assign):
        names = {name.name for name in assignment.find_all(nodes.Name)}
        if isinstance(assignment.target, nodes.Name) and names & aliases:
            aliases.add(assignment.target.name)
    constants = {assignment.target.name: assignment.node for assignment in tree.find_all(nodes.Assign)
                 if isinstance(assignment.target, nodes.Name)}
    for name in aliases:
        if isinstance(constants.get(name), nodes.Const):
            default = constants[name].value
    for expression in tree.find_all(nodes.Filter):
        names = {name.name for name in expression.find_all(nodes.Name)}
        if expression.name == "default" and names & aliases and expression.args and isinstance(expression.args[0], nodes.Const):
            default = expression.args[0].value
    values = []
    for comparison in tree.find_all(nodes.Compare):
        if not isinstance(comparison.expr, nodes.Name) or comparison.expr.name not in aliases:
            continue
        for operand in comparison.ops:
            expression = constants.get(operand.expr.name) if isinstance(operand.expr, nodes.Name) else operand.expr
            if operand.op in ("in", "notin") and isinstance(expression, (nodes.Tuple, nodes.List)):
                values = [item.value for item in expression.items if isinstance(item, nodes.Const)]
                break
            if operand.op in ('eq', 'ne') and isinstance(expression, nodes.Const) and isinstance(expression.value, str):
                values.append(expression.value)
        if operand.op in ('in', 'notin') and values:
            break
    if values:
        field.update(type="select", options=[{"label": "模型默认" + ("（" + str(default) + "）" if default else ""), "value": ""}] +
                     [{"label": value, "value": value} for value in dict.fromkeys(values)])
    return field
