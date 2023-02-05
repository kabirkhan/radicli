from typing import Callable, Any, List, Dict, Optional
import catalogue
from inspect import signature
from dataclasses import dataclass
import argparse

from .util import ArgparseArg, Arg, get_arg, get_type_name, SimpleFrozenDict


@dataclass
class Command:
    name: str
    func: Callable
    args: List[ArgparseArg]
    description: Optional[str]
    allow_extra: bool = False


class Radicli:
    def __init__(
        self,
        name: str,
        help: Optional[str] = None,
        converters: Dict[Any, Callable[[str], Any]] = SimpleFrozenDict(),
        extra_key: str = "_extra",
    ) -> None:
        """Initialize the CLI and create the registry."""
        self.name = name
        self.help = help
        self.converters = converters
        self.extra_key = extra_key
        self.registry = catalogue.create(self.name, "commands")

    def command(self, name: str, **args) -> Callable[[Callable], Callable]:
        """The decorator used to wrap command functions."""
        return self._command(name, args, allow_extra=False)

    def command_with_extra(self, name: str, **args) -> Callable[[Callable], Callable]:
        """
        The decorator used to wrap command functions. Supports additional
        arguments, which are passed in as the keyword argument _extra as a list.
        """
        return self._command(name, args, allow_extra=True)

    def _command(
        self, name: str, args: Dict[str, Any], *, allow_extra: bool = False
    ) -> Callable[[Callable], Callable]:
        """The decorator used to wrap command functions."""

        def cli_wrapper(cli_func: Callable) -> Callable[[Callable], Callable]:
            sig = signature(cli_func)
            sig_types = {}
            sig_defaults = {}
            for param_name, param_value in sig.parameters.items():
                sig_types[param_name] = param_value.annotation
                sig_defaults[param_name] = (
                    param_value.default
                    if param_value.default != param_value.empty
                    else ...  # placeholder for unset defaults
                )
                if param_name not in args:  # support args not in decorator
                    args[param_name] = Arg()
            cli_args = []
            for param, arg in args.items():
                converter = self.converters.get(sig_types[param], arg.converter)
                arg_type = converter or sig_types[param]
                arg = get_arg(
                    param,
                    arg_type,
                    name=arg.option,
                    shorthand=arg.short,
                    help=arg.help,
                    default=sig_defaults[param],
                    skip_resolve=converter is not None,
                )
                arg.help = f"({get_type_name(arg_type)}) {arg.help or ''}"
                cli_args.append(arg)
            cmd = Command(
                name=name,
                func=cli_func,
                args=cli_args,
                description=cli_func.__doc__,
                allow_extra=allow_extra,
            )
            self.registry.register(name, func=cmd)
            return cli_func

        return cli_wrapper

    def run(self) -> None:
        """
        Run the CLI. Should typically be used in the __main__.py nested under a
        `if __name__ == "__main__":` block.
        """
        import sys

        if len(sys.argv) <= 1 or sys.argv[1] == "--help":
            if self.help:
                print(f"\n{self.help}\n")
            commands = self.registry.get_all()
            if commands:
                print("Available commands:")
                for name, cmd in commands.items():
                    print(f"{name}\t{cmd.description or ''}")
        else:
            command = sys.argv.pop(1)
            args = sys.argv[1:]
            cmd = self.registry.get(command)
            values = self.parse(
                args, cmd.args, description=cmd.description, allow_extra=cmd.allow_extra
            )
            cmd.func(**values)

    def parse(
        self,
        args: List[str],
        arg_info: List[ArgparseArg],
        *,
        description: Optional[str] = None,
        allow_extra: bool = False,
    ) -> Dict[str, Any]:
        """Parse a list of arguments. Can also be used for testing."""
        p = argparse.ArgumentParser(description=description)
        for arg in arg_info:
            if arg.id == self.extra_key:
                continue
            func_args, func_kwargs = arg.to_argparse()
            p.add_argument(*func_args, **func_kwargs)
        if allow_extra:
            namespace, extra = p.parse_known_args(args)
            return {**vars(namespace), self.extra_key: extra}
        else:
            return vars(p.parse_args(args))
