"""The deterministic verifier: each tool's checks live in its own module, on contract instances."""

from contract import Task, Tool

from . import alerts, generate, inspect_service, inspect_services, root_cause, trace_services

TOOLS = {
    Tool.GENERATE_OUTAGE: generate,
    Tool.LIST_ALERTS: alerts,
    Tool.INSPECT_SERVICE: inspect_service,
    Tool.INSPECT_SERVICES: inspect_services,
    Tool.TRACE_SERVICES: trace_services,
}


def _tool_output(module):
    """A tool task's check: its output judged as its one tool's verify_output judges it."""
    return lambda arguments, output, reference, workspace: module.verify_output(arguments, output, workspace)


# task -> its output's check, verify_task(arguments, output, reference, workspace)
TASKS = {
    Task.GENERATE_OUTAGE: _tool_output(generate),
    Task.LIST_ALERTS: _tool_output(alerts),
    Task.INSPECT_SERVICE: _tool_output(inspect_service),
    Task.FIND_ROOT_CAUSE: root_cause.verify_task,
}


def verify_input(tool, value):
    return TOOLS[Tool(tool)].verify_input(value)


def verify_output(tool, input_value, output_value, workspace):
    return TOOLS[Tool(tool)].verify_output(input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
