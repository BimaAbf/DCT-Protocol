import colorama
from colorama import Fore
import sys

colorama.init(autoreset=True)


class _Logger:
    def _print_color(self, color, *args, **kwargs):
            # We join args with a space to mimic print() behavior.
        # 'kwargs' are passed to print (e.g., end='\n', sep=' ')
        text = " ".join(map(str, args))
        print(color + text, **kwargs)

    def red(self, *args, **kwargs):
        self._print_color(Fore.RED, *args, **kwargs)

    def green(self, *args, **kwargs):
        self._print_color(Fore.GREEN, *args, **kwargs)

    def blue(self, *args, **kwargs):
        self._print_color(Fore.BLUE, *args, **kwargs)

    def yellow(self, *args, **kwargs):
        self._print_color(Fore.YELLOW, *args, **kwargs)

    def text(self, *args, **kwargs):
        print(*args, **kwargs)


class _Console:
    def __init__(self):
        self.log = _Logger()

console = _Console()