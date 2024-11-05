"""Utilities for methods in modules and classes"""

import ast
import importlib.util
import inspect
import logging
import os
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class FoundMethod:
    """A method found in module or class"""

    method_name: str
    func_def: ast.FunctionDef
    package_name: str
    class_name: str
    doc_string: str
    parameters: str


def parse_function_arguments(func_node):
    """
    Parse the arguments of a function node and return details as a dictionary.
    """
    args_info = {}
    arguments = func_node.args

    # Handle positional arguments
    for arg in arguments.args:
        arg_name = arg.arg
        arg_default = None
        if arguments.defaults:
            default_index = len(arguments.args) - len(arguments.defaults)
            if arguments.args.index(arg) >= default_index:
                arg_default = arguments.defaults[
                    arguments.args.index(arg) - default_index
                ]
                arg_default = ast.literal_eval(arg_default)
        args_info[arg_name] = {
            "default": arg_default,
            "annotation": ast.dump(arg.annotation) if arg.annotation else None,
        }

    # Handle keyword-only arguments
    for kwarg in arguments.kwonlyargs:
        kwarg_name = kwarg.arg
        kwarg_default = None
        if arguments.kw_defaults:
            kwarg_default = arguments.kw_defaults[arguments.kwonlyargs.index(kwarg)]
            if kwarg_default is not None:
                kwarg_default = ast.literal_eval(kwarg_default)
        args_info[kwarg_name] = {
            "default": kwarg_default,
            "annotation": ast.dump(kwarg.annotation) if kwarg.annotation else None,
        }

    # Handle *args
    if arguments.vararg:
        vararg_name = arguments.vararg.arg
        args_info[vararg_name] = {
            "default": None,
            "annotation": (
                ast.dump(arguments.vararg.annotation)
                if arguments.vararg.annotation
                else None
            ),
        }

    # Handle **kwargs
    if arguments.kwarg:
        kwarg_name = arguments.kwarg.arg
        args_info[kwarg_name] = {
            "default": None,
            "annotation": (
                ast.dump(arguments.kwarg.annotation)
                if arguments.kwarg.annotation
                else None
            ),
        }

    return args_info


def find_method_direct(method_name_full: str, expected_num: int = 1):
    """Find a specified method with full name"""
    methods = []

    module_name, method_name = method_name_full.rsplit(".", 1)
    # Special case for requests
    if module_name == "requests":
        module_name = "requests.api"
    importlib.import_module(module_name)
    spec = importlib.util.find_spec(module_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # method = getattr(module, method_name)
    parsed_content = ast.parse(inspect.getsource(module))
    for node in ast.walk(parsed_content):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            found_method = FoundMethod(
                method_name=method_name_full,
                func_def=node,
                package_name=module_name,
                class_name=None,
                doc_string=ast.get_docstring(node),
                parameters=parse_function_arguments(node),
            )
            methods.append(found_method)
            if len(methods) >= expected_num:
                return methods


def find_method_in_packages(
    package_names: list, method_name: str, class_name: str = None, expected_num: int = 1
) -> List[FoundMethod]:
    """
    Find a method in given list of packages (self.package_names),
    which are already installed.

    :param str method_name: The method name to find. If '*' then return
        every method, with expected_num limit.
    :param str class_name: (optional) Class name to match.
    :param expected_num: (optional) Maximum num to return, default 1.
        If -1 then no limit.
    :return: A list of method in FoundMethod objects.
    """
    methods = []

    for package_name in package_names:
        package_spec = importlib.util.find_spec(package_name)
        if package_spec is None:
            logger.error("Package %s not found", package_name)
            continue

        package_path = package_spec.submodule_search_locations[0]
        methods += _find_methods_in_package(
            package_path, package_name, method_name, class_name, expected_num
        )

        if len(methods) >= expected_num != -1:
            return methods

    if not methods:
        logger.error(
            "Error: Method %s cannot be located in known packages.", method_name
        )
    return methods


def _find_methods_in_package(
    package_path, package_name, method_name, class_name, expected_num
) -> List[FoundMethod]:
    """
    Find methods in a specific package path.
    """
    methods = []
    for root, _, files in os.walk(package_path):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                methods += _find_methods_in_file(
                    file_path, package_name, method_name, class_name, expected_num
                )

                if len(methods) >= expected_num != -1:
                    return methods

    return methods


def _find_methods_in_file(
    file_path, package_name, method_name, class_name, expected_num
) -> List[FoundMethod]:
    """
    Find methods in a specific file.
    """
    methods = []
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            parsed_content = ast.parse(f.read())
            for node in ast.walk(parsed_content):
                if not isinstance(node, ast.ClassDef):
                    continue
                for item in node.body:
                    if class_name and class_name != node.name:
                        continue
                    if not isinstance(item, ast.FunctionDef) or method_name not in [
                        item.name,
                        "*",
                    ]:
                        continue
                    methods.append(
                        FoundMethod(
                            method_name=item.name,
                            func_def=item,
                            package_name=package_name,
                            class_name=node.name,
                            doc_string=ast.get_docstring(item),
                            parameters=None,  # parse_function_arguments(item),
                        )
                    )
                    if len(methods) >= expected_num != -1:
                        return methods
            return methods
        except (SyntaxError, UnicodeDecodeError):
            logger.error("Error parsing file %s", file_path)
            return
