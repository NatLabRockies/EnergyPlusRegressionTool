from contextlib import redirect_stdout
from io import StringIO
from unittest import TestCase

from energyplus_regressions.results import ResultsManager


import re


def is_probably_valid_html(html: str):
    void_elements = {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr", "command", "keygen", "menuitem"  # last 3 are legacy
    }

    # precompiled patterns
    comments = re.compile(r"<!--.*?-->", re.DOTALL)
    declarations = re.compile(r"<![^>-][^>]*?>|<\?[^>]*?\?>", re.DOTALL)  # <!DOCTYPE...>, <!something>, <?...?>
    tag = re.compile(r"</?\s*([a-zA-Z][a-zA-Z0-9:-]*)\b[^>]*?/?>", re.DOTALL)

    # strip comments and declarations so they don't confuse tag scanning
    s = comments.sub("", html)
    s = declarations.sub("", s)

    stack = []
    for m in tag.finditer(s):
        raw = m.group(0)
        name = m.group(1).lower()

        # self-closing like <tag ... />
        self_closing = raw.rstrip().endswith("/>")
        closing = raw.startswith("</")

        if closing:
            if not stack:
                return False, f"Unexpected closing </{name}> at index {m.start()}."
            top = stack.pop()
            if top != name:
                return False, f"Mismatched closing </{name}> at index {m.start()} (expected </{top}>)."
        else:
            # opening tag
            if name in void_elements or self_closing:
                continue
            stack.append(name)

    if stack:
        # report the first unclosed tag (and how many more)
        first = stack[-1]
        extra = len(stack) - 1
        if extra:
            return False, f"Unclosed <{first}> and {extra} more tag(s)."
        else:
            return False, f"Unclosed <{first}>."
    return True, "Looks OK: tags are balanced (heuristic)."


# --- quick demos ---
tests = [
    "<div><p>hi</p></div>",
    "<div><img src=x><br></div>",
    "<ul><li>one<li>two</ul>",            # li can omit close in HTML, but we'll flag it
    "<div><span>oops</div>",
    "<div><input type=text></div>",
    "<!-- comment --><p>ok</p>",
    "<!DOCTYPE html><html><body><hr></body></html>",
]
for t in tests:
    print(is_probably_valid_html(t))


class TestRegressionManager(TestCase):
    def test_printer(self):
        r = ResultsManager(mute=True)
        buf = StringIO()
        with redirect_stdout(buf):
            r.print("Hello")
        output = buf.getvalue()
        self.assertEqual("", output)
        r = ResultsManager(mute=False)
        buf = StringIO()
        with redirect_stdout(buf):
            r.print("Hello")
        output = buf.getvalue()
        self.assertEqual("Hello\n", output)

    def test_html_wrapper(self):
        contents = "Hi"
        html_wrapped = ResultsManager.embed_diff_contents_in_html_wrapper(contents)
        self.assertIn("<html>", html_wrapped)  # should be the outermost html tag
        self.assertIn(contents, html_wrapped)  # and should contain the contents we passed in

    # def single_test_case_row(self):
