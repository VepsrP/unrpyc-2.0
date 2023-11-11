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

    def print_node(self, ast, indent):
        self.dispatch.get(type(ast), type(self).print_unknown)(self, ast, indent)

    def print_nodes(self, ast, indent=0):
        for i, node in enumerate(ast):
            node = convert_ast(node)
            self.print_node(node, indent)

    def print_atl(self, ast, indent):
        ast = convert_ast(ast)
        if ast.statements:
            self.print_nodes(ast.statements, indent + 1)
        # If a statement ends with a colon but has no block after it, loc will
        # get set to ('', 0). That isn't supposed to be valid syntax, but it's
        # the only thing that can generate that.
        elif ast.loc != ('', 0):
            lines[ast.loc[1]] = (indent+1, "pass")

    @dispatch(renpy.atl.RawMultipurpose)
    def print_atl_rawmulti(self, ast, indent):
        warp_words = WordConcatenator(False)
        ast = convert_ast(ast)
        # warpers
        if ast.warp_function:
            warp_words.append("warp", ast.warp_function, ast.duration)
        elif ast.warper:
            warp_words.append(ast.warper, ast.duration)
        elif ast.duration != "0" and ast.duration != b"0":
            warp_words.append("pause", ast.duration)
        warp = warp_words.join()
        words = WordConcatenator(warp and warp[-1] != ' ', True)

        # revolution
        if ast.revolution:
            words.append(ast.revolution)

        # circles
        if ast.circles != "0":
            words.append("circles %s" % ast.circles)

        # splines
        spline_words = WordConcatenator(False)
        for name, expressions in ast.splines:
            spline_words.append(name, expressions[-1])
            for expression in expressions[:-1]:
                spline_words.append("knot", expression)
        words.append(spline_words.join())

        # properties
        property_words = WordConcatenator(False)
        for key, value in ast.properties:
            property_words.append(key, value)
        words.append(property_words.join())

        # with
        expression_words = WordConcatenator(False)
        # TODO There's a lot of cases where pass isn't needed, since we could
        # reorder stuff so there's never 2 expressions in a row. (And it's never
        # necessary for the last one, but we don't know what the last one is
        # since it could get reordered.)
        needs_pass = len(ast.expressions) > 1
        for (expression, with_expression) in ast.expressions:
            expression_words.append(expression)
            if with_expression:
                expression_words.append("with", with_expression)
            if needs_pass:
                expression_words.append("pass")
        words.append(expression_words.join())

        to_write = warp + words.join()
        if to_write:
            lines[ast.loc[1]] = (indent, to_write)
        else:
            # A trailing comma results in an empty RawMultipurpose being
            # generated on the same line as the last real one.
            lines[ast.loc[1]] = (indent, ",")