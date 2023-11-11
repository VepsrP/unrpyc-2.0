# Copyright (c) 2012 Yuri K. Schlesner
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import unicode_literals
from .util import DecompilerBase, First, WordConcatenator, reconstruct_paraminfo, \
    reconstruct_arginfo, string_escape, split_logical_lines, Dispatcher, convert_ast
from .util import say_get_code

from operator import itemgetter
from io import StringIO
import importlib
if (hasattr(importlib, 'reload')):
    from importlib import reload
from . import magic
import renpy

magic.fake_package("renpy")
store = magic.fake_package("store")
renpy = reload(renpy)

from . import screendecompiler
from . import sl2decompiler
from . import testcasedecompiler
from . import codegen
from . import astdump
import sys
PY2 = sys.version_info < (3, 0)
PY3 = not PY2

__all__ = ["astdump", "codegen", "magic", "screendecompiler", "sl2decompiler", "testcasedecompiler", "translate", "util", "pprint", "Decompiler"]

# Main API

lines = dict()

def pprint(out_file, ast, indent_level=0,
           decompile_python=False, printlock=None, translator=None, init_offset=False, tag_outside_block=False):
    Decompiler(out_file, printlock=printlock,
               decompile_python=decompile_python, translator=translator).dump(ast, indent_level, init_offset, tag_outside_block)

class Decompiler(DecompilerBase):

    dispatch = Dispatcher()

    def print_node(self, ast):
        self.dispatch.get(type(ast), type(self).print_unknown)(self, ast)

    def print_atl(self, ast, indent):
        ast = convert_ast(ast)
        if ast.statements:
            self.print_nodes(ast.statements, indent)
        # If a statement ends with a colon but has no block after it, loc will
        # get set to ('', 0). That isn't supposed to be valid syntax, but it's
        # the only thing that can generate that.
        elif ast.loc != ('', 0):
            lines[ast.loc[1]] = (indent+1, "pass")