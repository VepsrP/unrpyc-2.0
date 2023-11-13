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

    @dispatch(renpy.atl.RawBlock)
    @dispatch(store.ATL.RawBlock)
    def print_atl_rawblock(self, ast, indent):
        lines[ast.loc[1]-1] = (indent, "block:")
        self.print_atl(ast, indent + 1)

    @dispatch(renpy.atl.RawChild)
    def print_atl_rawchild(self, ast, indent):
        for child in ast.children:
            lines[ast.loc[1]] = (indent, "contains:")
            self.print_atl(child, indent + 1)

    # @dispatch(renpy.atl.RawChoice)
    # def print_atl_rawchoice(self, ast, indent):
    #     for chance, block in ast.choices:

    #         self.indent()
    #         self.write("choice")
    #         if chance != "1.0":
    #             self.write(" %s" % chance)
    #         self.write(":")
    #         self.print_atl(block)
    #     if (self.index + 1 < len(self.block) and
    #     	isinstance(self.block[self.index + 1], renpy.atl.RawChoice)):
    #         self.indent()
    #         self.write("pass")

    # @dispatch(store.ATL.RawChoice)
    # def print_atl_rawchoice(self, ast):
    #     for loc, chance, block in ast.choices:
    #         self.indent()
    #         self.write("choice")
    #         if chance != "1.0":
    #             self.write(" %s" % chance)
    #         self.write(":")
    #         self.print_atl(block)
    #     if (self.index + 1 < len(self.block) and
    #     	isinstance(self.block[self.index + 1], renpy.atl.RawChoice)):
    #         self.indent()
    #         self.write("pass")

    # @dispatch(renpy.atl.RawContainsExpr)
    # def print_atl_rawcontainsexpr(self, ast, indent):
    #     lines[]
    #     self.write("contains %s" % ast.expression)

    # @dispatch(renpy.atl.RawEvent)
    # def print_atl_rawevent(self, ast):
    #     self.indent()
    #     self.write("event %s" % ast.name)

    @dispatch(renpy.atl.RawFunction)
    def print_atl_rawfunction(self, ast, indent):
        lines[ast.loc[1]] = (indent, "function %s" % ast.expr)

    @dispatch(renpy.atl.RawOn)
    def print_atl_rawon(self, ast, indent):
        for name, block in sorted(ast.handlers.items(),
                                  key=lambda i: i[1].loc[1]):
            lines[block.loc[1] - 1] = (indent, "on %s:" % name)
            self.print_atl(block, indent + 1)

    @dispatch(renpy.atl.RawParallel)
    def print_atl_rawparallel(self, ast, indent):
        for block in ast.blocks:
            lines[block.loc[1] - 1] = (indent, "parallel:")
            self.print_atl(block, indent + 1)
        if (self.index + 1 < len(self.block) and
            isinstance(self.block[self.index + 1], renpy.atl.RawParallel)):
            self.write("pass")

    @dispatch(renpy.atl.RawRepeat)
    @dispatch(store.ATL.RawRepeat)
    def print_atl_rawrepeat(self, ast, indent):
        lines[ast.loc[1]] = (indent, "repeat")
        if ast.repeats:
            lines[ast.loc[1]][1] += " %s" % ast.repeats # not sure if this is even a string

    @dispatch(renpy.atl.RawTime)
    def print_atl_rawtime(self, ast, indent):
        lines[ast.loc[1]] = (indent, "time %s" % ast.time)

    def print_imspec(self, imspec):
        return False
    
    @dispatch(renpy.ast.Image)
    def print_image(self, ast, indent):
        self.require_init()
        lines[ast.loc[1]] = (indent, "image %s" % ' '.join(ast.imgname))
        if ast.code is not None:
            lines[ast.loc[1]][1] += " = %s" % ast.code.source
        else:
            if hasattr(ast, "atl") and ast.atl is not None:
                lines[ast.loc[1]][1] += ":"
                self.print_atl(ast.atl, indent + 1)

    @dispatch(renpy.ast.Transform)
    def print_transform(self, ast, indent):
        self.require_init()

        # If we have an implicit init block with a non-default priority, we need to store the priority here.
        priority = ""
        if isinstance(self.parent, renpy.ast.Init):
            init = self.parent
            if init.priority != self.init_offset and len(init.block) == 1 and not self.should_come_before(init, ast):
                priority = " %d" % (init.priority - self.init_offset)
        lines[ast.loc[1]] = (indent, "transform%s %s" % (priority, ast.varname))
        if ast.parameters is not None:
            lines[ast.loc[1]][1] += reconstruct_paraminfo(ast.parameters)

        if hasattr(ast, "atl") and ast.atl is not None:
            lines[ast.loc[1]][1] += ":"
            self.print_atl(ast.atl, indent + 1)

    # Directing related functions

    @dispatch(renpy.ast.Show)
    def print_show(self, ast, indent):
        lines[ast.loc[1]] = (indent, "show ")
        needs_space = self.print_imspec(ast.imspec)

        if self.paired_with:
            if needs_space:
                lines[ast.loc[1]][1] += " "
            lines[ast.loc[1]][1] += "with %s" % self.paired_with
            self.paired_with = True

        if hasattr(ast, "atl") and ast.atl is not None:
            lines[ast.loc[1]][1] += ":"
            self.print_atl(ast.atl, indent + 1)

    @dispatch(renpy.ast.ShowLayer)
    def print_showlayer(self, ast, indent):
        lines[ast.loc[1]] = (indent, "show layer %s" % ast.layer)

        if ast.at_list:
            lines[ast.loc[1]][1] += " at %s" % ', '.join(ast.at_list)

        if hasattr(ast, "atl") and ast.atl is not None:
            lines[ast.loc[1]][1] += ":"
            self.print_atl(ast.atl, indent + 1)

    @dispatch(renpy.ast.Scene)
    def print_scene(self, ast, indent):
        lines[ast.loc[1]] = (indent, "scene")

        if ast.imspec is None:
            if (PY2 and isinstance(ast.layer, unicode) or (PY3 and isinstance(ast.layer, str))):
                    lines[ast.loc[1]][1] += " onlayer %s" % ast.layer

            needs_space = True
        else:
            lines[ast.loc[1]][1] += " "
            needs_space = self.print_imspec(ast.imspec)

        if self.paired_with:
            if needs_space:
                lines[ast.loc[1]][1] += " "
            lines[ast.loc[1]][1] += "with %s" % self.paired_with
            self.paired_with = True

        if hasattr(ast, "atl") and ast.atl is not None:
            lines[ast.loc[1]][1] += ":"
            self.print_atl(ast.atl, indent + 1)

    @dispatch(renpy.ast.Hide)
    def print_hide(self, ast, indent):
        lines[ast.loc[1]] = (indent, "hide ")
        needs_space = self.print_imspec(ast.imspec)
        if self.paired_with:
            if needs_space:
                lines[ast.loc[1]][1] += " "
            lines[ast.loc[1]][1] += "with %s" % self.paired_with
            self.paired_with = True

    # @dispatch(renpy.ast.With)
    # def print_with(self, ast, indent):
    #     # the 'paired' attribute indicates that this with
    #     # and with node afterwards are part of a postfix
    #     # with statement. detect this and process it properly
    #     if hasattr(ast, "paired") and ast.paired is not None:
    #         self.block[self.index + 2] = convert_ast(self.block[self.index + 2])
    #         # Sanity check. check if there's a matching with statement two nodes further
    #         if not(isinstance(self.block[self.index + 2], renpy.ast.With) and
    #                self.block[self.index + 2].expr == ast.paired):
    #             raise Exception("Unmatched paired with {0} != {1}".format(
    #                             repr(self.paired_with), repr(ast.expr)))

    #         self.paired_with = ast.paired

    #     elif self.paired_with:
    #         # Check if it was consumed by a show/scene statement
    #         if self.paired_with is not True:
    #             self.write(" with %s" % ast.expr)
    #         self.paired_with = False
    #     else:
    #         self.advance_to_line(ast.linenumber)
    #         self.indent()
    #         self.write("with %s" % ast.expr)
    #         self.paired_with = False

    # @dispatch(renpy.ast.Label)
    # def print_label(self, ast):
    #     # If a Call block preceded us, it printed us as "from"
    #     if (self.index and isinstance(self.block[self.index - 1], renpy.ast.Call)):
    #         return
    #     remaining_blocks = len(self.block) - self.index
    #     if remaining_blocks > 1:
    #         next_ast = self.block[self.index + 1]
    #         # See if we're the label for a menu, rather than a standalone label.
    #         if (not ast.block and (not hasattr(ast, 'parameters') or ast.parameters is None) and
    #             hasattr(next_ast, 'linenumber') and next_ast.linenumber == ast.linenumber and
    #             (isinstance(next_ast, renpy.ast.Menu) or (remaining_blocks > 2 and
    #             isinstance(next_ast, renpy.ast.Say) and
    #             self.say_belongs_to_menu(next_ast, self.block[self.index + 2])))):
    #             self.label_inside_menu = ast
    #             return
    #     self.advance_to_line(ast.linenumber)
    #     self.indent()

    #     # It's possible that we're an "init label", not a regular label. There's no way to know
    #     # if we are until we parse our children, so temporarily redirect all of our output until
    #     # that's done, so that we can squeeze in an "init " if we are.
    #     out_file = self.out_file
    #     self.out_file = StringIO()
    #     missing_init = self.missing_init
    #     self.missing_init = False
    #     try:
    #         self.write("label %s%s%s:" % (
    #             ast.name,
    #             reconstruct_paraminfo(ast.parameters) if hasattr(ast, 'parameters') else '',
    #             " hide" if hasattr(ast, 'hide') and ast.hide else ""))
    #         self.print_nodes(ast.block, 1)
    #     finally:
    #         if self.missing_init:
    #             out_file.write("init ")
    #         self.missing_init = missing_init
    #         out_file.write(self.out_file.getvalue())
    #         self.out_file = out_file

    @dispatch(renpy.ast.Jump)
    def print_jump(self, ast, indent):
        lines[ast.linenumber] = (indent, "jump %s%s" % ("expression " if ast.expression else "", ast.target))

    # @dispatch(renpy.ast.Call)
    # def print_call(self, ast, indent):
    #     words = WordConcatenator(False)
    #     words.append("call")
    #     if ast.expression:
    #         words.append("expression")
    #     words.append(ast.label)

    #     if hasattr(ast, 'arguments') and ast.arguments is not None:
    #         if ast.expression:
    #             words.append("pass")
    #         words.append(reconstruct_arginfo(ast.arguments))

    #     # We don't have to check if there's enough elements here,
    #     # since a Label or a Pass is always emitted after a Call.
    #     next_block = convert_ast(self.block[self.index + 1])
    #     if isinstance(next_block, renpy.ast.Label):
    #         words.append("from %s" % next_block.name)

    #     lines[ast.linenumber] = (indent, words.join())

    # @dispatch(renpy.ast.Return)
    # def print_return(self, ast, indent):
    #     if ((not hasattr(ast, 'expression') or ast.expression is None) and self.parent is None and
    #         self.index + 1 == len(self.block) and self.index and
    #         ast.linenumber == self.block[self.index - 1].linenumber):
    #         # As of Ren'Py commit 356c6e34, a return statement is added to
    #         # the end of each rpyc file. Don't include this in the source.
    #         return

    #     lines[ast.linenumber] = (indent, "return")

    #     if hasattr(ast, 'expression') and ast.expression is not None:
    #         lines[ast.linenumber][1] += " %s" % ast.expression

    @dispatch(renpy.ast.If)
    def print_if(self, ast, indent):
        statement = First("if %s:", "elif %s:")

        for i, (condition, block) in enumerate(ast.entries):
            # The non-Unicode string "True" is the condition for else:

            if((i > 0) and (i + 1) == len(ast.entries) and ((PY2 and not isinstance(condition, unicode)) or (PY3 and not isinstance(condition, str)) or condition == u'True')):
                lines[block[0].linenumber - 1] = (indent, "else:")
            else:
                if(hasattr(condition, 'linenumber')):
                    lines[condition.linenumber] = (indent, statement() % condition)
                else:
                    lines[block[0].linenumber - 1] = (indent, statement() % condition)
            self.print_nodes(block, indent + 1)