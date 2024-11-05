"""Represents Tool Specification"""

import json
from dataclasses import dataclass
from typing import Optional

from docstring_parser import parse
from llama_index.core.tools.types import ToolMetadata


@dataclass
class ToolMetadataWithSpec(ToolMetadata):
    """Override ToolMetadata to add spec data"""

    tool_spec: Optional[str] = None


class ToolSpec:
    """Represents Tool Specification"""

    def __init__(
        self,
        name: str = None,
        description: str = None,
        param_props: dict = None,
        param_required: list = None,
    ):
        self.name = name or ""
        self.description = description or ""
        self.param_props = param_props or {}
        self.param_required = param_required or []

    def _get_parameters(self):
        return {
            "type": "object",
            "properties": self.param_props,
            "required": self.param_required,
        }

    def create_from_docstring(self, name: str, docstring: str):
        """
        Load function spec from Python function's definition docstring
        """
        self.name = name

        doc_dict = parse(docstring)
        self.description = doc_dict.long_description

        for param in doc_dict.params:
            param_obj = {
                "type": param.type_name,
                "description": param.description,
            }
            self.param_props[param.arg_name] = param_obj
            if not param.is_optional and "optional" not in param.description:
                self.param_required.append(param.arg_name)

    def create_from_schema_json(self, function_spec: dict):
        """
        Parses an OpenAI function tool spec into tool name, description, and parameter objects.
        """
        # If under 'function' key
        if "type" in function_spec.keys() and function_spec["type"] == "function":
            function_spec = function_spec["function"]

        self.name = function_spec.get("name", "")
        self.description = function_spec.get("description", "")

        params = function_spec.get("parameters", {})
        # Adapt cases when 'properties' omitted
        param_props = params.get("properties", params)

        for param_name, param_details in param_props.items():
            param_obj = {
                # Default to string if type is not specified
                "type": param_details.get("type", "string"),
                "description": param_details.get("description", ""),
            }
            self.param_props[param_name] = param_obj

        self.param_required = params.get("required", [])

    def __str__(self):
        return self.get_spec_json()

    def get_spec_dict(self, function_tag: bool = False):
        """Return a dict for spec"""
        if not self.param_props:
            self.param_props = {}

        spec = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {k: v for k, v in self.param_props.items()},
                "required": self.param_required,
            },
        }

        if function_tag:
            spec = {"type": "function", "function": spec}
        return spec

    def get_spec_json(self):
        """Return JSON format"""
        return json.dumps(self.get_spec_dict())

    def get_python_def(self):
        """
        Create Python function def statements
        """
        return
