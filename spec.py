"""Create function specs for FC LLMs, from sources of OpenAPI spec, or Python modules"""

import argparse
import json
import logging
import os
from pathlib import Path

import jsonref
from rich.logging import RichHandler

from toolspec import ToolSpec
from util import methods, text

logging.getLogger().handlers.clear()
logging.basicConfig(
    level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
)
logger = logging.getLogger(__name__)


def openapi_to_requests(openapi_spec):
    """Convert function's OpenAPI spec into requests' parameters spec"""

    functions = {}
    function_name = "requests"

    servers_urls = [s["url"] for s in openapi_spec["servers"]]

    for path, path_methods in openapi_spec["paths"].items():
        params_common_list = []
        for method, spec_with_ref in path_methods.items():
            # Commom parameters: 'path' level parameter in 'parameters'
            if method == "parameters":
                params_common_list = spec_with_ref
                continue

            # 1. Resolve JSON references.
            spec = jsonref.replace_refs(spec_with_ref)

            # 2. Extract a name for the functions.
            operation_id = spec.get("operationId")
            # Ensure normalized for file & path name
            operation_id=text.normalize_string(operation_id)

            logger.debug("Path [%s] method [%s] operationId [%s]", path, method, operation_id)
            function = {
                "name": f"{function_name}.{method}",
                "description": f"Sends a {method.upper()} request to the specified URL.",
                "parameters": {
                    "type": "dict",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": f"{spec.get("summary","")}. {spec.get("description","")}",
                            "enum": [
                                f"{url}{path}" for url in servers_urls # 'path' should have leading '/'
                            ],
                            "required": True
                        },
                        "headers": {
                            param["name"]: {
                                **(param.get("schema") if "schema" in param else {"type": param["type"]}),
                                **{
                                    k: v
                                    for k, v in param.items()
                                    if k not in ["name", "in", "schema"]
                                },
                            }
                            for param in params_common_list + spec.get("parameters", [])
                            if param["in"] == "header"
                        },
                        "timeout": {
                            "type": ["number", "tuple"],
                            "description": "How many seconds to wait for the server to send data before giving up.",
                            "required": False,
                        },
                        "params": {
                            param["name"]: {
                                **(param.get("schema") if "schema" in param else {"type": param["type"]}),
                                **{
                                    k: v
                                    for k, v in param.items()
                                    if k not in ["name", "in", "schema"]
                                },
                            }
                            for param in params_common_list + spec.get("parameters", [])
                            if param["in"] == "query"
                        },
                        "data": spec.get("requestBody").get("content")
                            # 'application/json', 'application/x-www-form-urlencoded', ...
                            .get(next(iter(spec.get("requestBody").get("content"))))
                            .get("schema").get("properties")
                            if "requestBody" in spec else {}
                    },
                },
            }

            functions[operation_id] = function

    return functions

def modules_to_spec(module_name, class_name):
    """Create function specs for Python methods in module or module.class"""
    functions = {}

    # If no class specified, enumerate all classes first
    # Only accept class methods?

    any_method_name = '*'
    logger.info("Module [%s] Class [%s]", module_name, class_name)
    found = methods.find_method_in_packages(package_names=[module_name],method_name=any_method_name,
                                            class_name=class_name,expected_num=-1)
    if not found:
        logger.error("Failed to find methods in [%s]", module_name)
        return None
    
    for method in found:
        method_name = method.method_name
        
        if method_name[0] == '_' or method_name in [ "new_instance" ]: # internal method
            logger.debug("Method: [%s] skipped", method_name)
            continue

        # Create spec - Param definitions from ast, docstring for descriptions
        # p = launcher.parse_function_arguments(method.func_def)
        # print(ast.dump(method.func_def))
        # p = ast_helper.get_function_parameters(method.func_def)
        logger.debug("Method: [%s]", method_name)
        spec=ToolSpec()
        spec.create_from_docstring(method_name, method.doc_string)
        function = spec.get_spec_dict()
        functions[method_name] = function

    return functions

def write_specs(functions, fname_base, dest_dir:str="functions"):
    """Write function specs to JSON files"""
    # To be more LLM context friendly, one API per JSON file
    for function_name, function in functions.items():
        fname = f"{function_name}.json"
        os.makedirs(f"{dest_dir}/{fname_base}", exist_ok=True)
        with open(f"{dest_dir}/{fname_base}/{fname}", "w", encoding="utf-8") as of:
            of.write(json.dumps(function, indent=4))
        logger.info("Output: %s", f"{dest_dir}/{fname_base}/{fname}")


def main():
    """Spec creation utility"""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Verbose output."
    )
    parser.add_argument(
        "-d",
        "--dest_dir",
        help="Destination folder for generated JSONs. Default 'functions'",
        default="functions",
    )
    parser.add_argument(
        "-s", "--source_file", help="Source OpenAPI JSON file", required=False
    )
    parser.add_argument(
        "-p", "--python_module", help="Python 'module_name' or 'module_name.class_name'", required=False
    )

    args = parser.parse_args()

    log_level_root = logging.INFO
    match args.verbose:
        case v if 1 <= v:
            log_level_root = logging.DEBUG
    # Configure logging for global
    logging.getLogger().handlers.clear()
    logging.basicConfig(
        level=log_level_root,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler()],
    )

    # Create spec for REST API from OpenAPI spec
    if args.source_file:
        with open(args.source_file, encoding="utf-8") as f:
            # it's important to load with jsonref, as explained below
            openapi_spec = jsonref.loads(f.read())
        functions = openapi_to_requests(openapi_spec)
        write_specs(functions, Path(args.source_file).stem, args.dest_dir)

    # Create spec for Python methods from Python code
    if args.python_module: # can be "module_name" or "moudle_name.class_name"
        module_class = args.python_module
        p = module_class.rsplit('.', maxsplit=1)
        module_name=p[0]
        class_name = p[1] if len(p) == 2 else None
        functions = modules_to_spec(module_name, class_name)
        write_specs(functions, module_name, args.dest_dir)

if __name__ == "__main__":
    main()
