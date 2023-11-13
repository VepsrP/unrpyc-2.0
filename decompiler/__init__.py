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

def pprint(out_file, ast, indent_level=0,
           decompile_python=False, printlock=None, translator=None, init_offset=False, tag_outside_block=False):
    Decompiler(out_file, printlock=printlock,
               decompile_python=decompile_python, translator=translator).dump(ast, indent_level, init_offset, tag_outside_block)

class Decompiler(DecompilerBase):

    lines = dict()

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
            self.self.lines[ast.loc[1]] = (indent+1, "pass")

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
            self.lines[ast.loc[1]] = (indent, to_write)
        else:
            # A trailing comma results in an empty RawMultipurpose being
            # generated on the same line as the last real one.
            self.lines[ast.loc[1]] = (indent, ",")

    @dispatch(renpy.atl.RawBlock)
    @dispatch(store.ATL.RawBlock)
    def print_atl_rawblock(self, ast, indent):
        self.lines[ast.loc[1]-1] = (indent, "block:")
        self.print_atl(ast, indent + 1)

    @dispatch(renpy.atl.RawChild)
    def print_atl_rawchild(self, ast, indent):
        for child in ast.children:
            self.lines[ast.loc[1]] = (indent, "contains:")
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
    #     self.lines[]
    #     self.write("contains %s" % ast.expression)

    # @dispatch(renpy.atl.RawEvent)
    # def print_atl_rawevent(self, ast):
    #     self.indent()
    #     self.write("event %s" % ast.name)

    @dispatch(renpy.atl.RawFunction)
    def print_atl_rawfunction(self, ast, indent):
        self.lines[ast.loc[1]] = (indent, "function %s" % ast.expr)

    @dispatch(renpy.atl.RawOn)
    def print_atl_rawon(self, ast, indent):
        for name, block in sorted(ast.handlers.items(),
                                  key=lambda i: i[1].loc[1]):
            self.lines[block.loc[1] - 1] = (indent, "on %s:" % name)
            self.print_atl(block, indent + 1)

    @dispatch(renpy.atl.RawParallel)
    def print_atl_rawparallel(self, ast, indent):
        for block in ast.blocks:
            self.lines[block.loc[1] - 1] = (indent, "parallel:")
            self.print_atl(block, indent + 1)
        if (self.index + 1 < len(self.block) and
            isinstance(self.block[self.index + 1], renpy.atl.RawParallel)):
            self.write("pass")

    @dispatch(renpy.atl.RawRepeat)
    @dispatch(store.ATL.RawRepeat)
    def print_atl_rawrepeat(self, ast, indent):
        self.lines[ast.loc[1]] = (indent, "repeat")
        if ast.repeats:
            self.lines[ast.loc[1]][1] += " %s" % ast.repeats # not sure if this is even a string

    @dispatch(renpy.atl.RawTime)
    def print_atl_rawtime(self, ast, indent):
        self.lines[ast.loc[1]] = (indent, "time %s" % ast.time)

    def print_imspec(self, imspec):
        return False
    
    @dispatch(renpy.ast.Image)
    def print_image(self, ast, indent):
        self.require_init()
        self.lines[ast.loc[1]] = (indent, "image %s" % ' '.join(ast.imgname))
        if ast.code is not None:
            self.lines[ast.loc[1]][1] += " = %s" % ast.code.source
        else:
            if hasattr(ast, "atl") and ast.atl is not None:
                self.lines[ast.loc[1]][1] += ":"
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
        self.lines[ast.loc[1]] = (indent, "transform%s %s" % (priority, ast.varname))
        if ast.parameters is not None:
            self.lines[ast.loc[1]][1] += reconstruct_paraminfo(ast.parameters)

        if hasattr(ast, "atl") and ast.atl is not None:
            self.lines[ast.loc[1]][1] += ":"
            self.print_atl(ast.atl, indent + 1)

    # Directing related functions

    @dispatch(renpy.ast.Show)
    def print_show(self, ast, indent):
        self.lines[ast.loc[1]] = (indent, "show ")
        needs_space = self.print_imspec(ast.imspec)

        if self.paired_with:
            if needs_space:
                self.lines[ast.loc[1]][1] += " "
            self.lines[ast.loc[1]][1] += "with %s" % self.paired_with
            self.paired_with = True

        if hasattr(ast, "atl") and ast.atl is not None:
            self.lines[ast.loc[1]][1] += ":"
            self.print_atl(ast.atl, indent + 1)

    @dispatch(renpy.ast.ShowLayer)
    def print_showlayer(self, ast, indent):
        self.lines[ast.loc[1]] = (indent, "show layer %s" % ast.layer)

        if ast.at_list:
            self.lines[ast.loc[1]][1] += " at %s" % ', '.join(ast.at_list)

        if hasattr(ast, "atl") and ast.atl is not None:
            self.lines[ast.loc[1]][1] += ":"
            self.print_atl(ast.atl, indent + 1)

    @dispatch(renpy.ast.Scene)
    def print_scene(self, ast, indent):
        self.lines[ast.loc[1]] = (indent, "scene")

        if ast.imspec is None:
            if (PY2 and isinstance(ast.layer, unicode) or (PY3 and isinstance(ast.layer, str))):
                    self.lines[ast.loc[1]][1] += " onlayer %s" % ast.layer

            needs_space = True
        else:
            self.lines[ast.loc[1]][1] += " "
            needs_space = self.print_imspec(ast.imspec)

        if self.paired_with:
            if needs_space:
                self.lines[ast.loc[1]][1] += " "
            self.lines[ast.loc[1]][1] += "with %s" % self.paired_with
            self.paired_with = True

        if hasattr(ast, "atl") and ast.atl is not None:
            self.lines[ast.loc[1]][1] += ":"
            self.print_atl(ast.atl, indent + 1)

    @dispatch(renpy.ast.Hide)
    def print_hide(self, ast, indent):
        self.lines[ast.loc[1]] = (indent, "hide ")
        needs_space = self.print_imspec(ast.imspec)
        if self.paired_with:
            if needs_space:
                self.lines[ast.loc[1]][1] += " "
            self.lines[ast.loc[1]][1] += "with %s" % self.paired_with
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
        self.lines[ast.linenumber] = (indent, "jump %s%s" % ("expression " if ast.expression else "", ast.target))

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

    #     self.lines[ast.linenumber] = (indent, words.join())

    # @dispatch(renpy.ast.Return)
    # def print_return(self, ast, indent):
    #     if ((not hasattr(ast, 'expression') or ast.expression is None) and self.parent is None and
    #         self.index + 1 == len(self.block) and self.index and
    #         ast.linenumber == self.block[self.index - 1].linenumber):
    #         # As of Ren'Py commit 356c6e34, a return statement is added to
    #         # the end of each rpyc file. Don't include this in the source.
    #         return

    #     self.lines[ast.linenumber] = (indent, "return")

    #     if hasattr(ast, 'expression') and ast.expression is not None:
    #         self.lines[ast.linenumber][1] += " %s" % ast.expression

    @dispatch(renpy.ast.If)
    def print_if(self, ast, indent):
        statement = First("if %s:", "elif %s:")

        for i, (condition, block) in enumerate(ast.entries):
            # The non-Unicode string "True" is the condition for else:

            if((i > 0) and (i + 1) == len(ast.entries) and ((PY2 and not isinstance(condition, unicode)) or (PY3 and not isinstance(condition, str)) or condition == u'True')):
                self.lines[block[0].linenumber - 1] = (indent, "else:")
            else:
                if(hasattr(condition, 'linenumber')):
                    self.lines[condition.linenumber] = (indent, statement() % condition)
                else:
                    self.lines[block[0].linenumber - 1] = (indent, statement() % condition)
            self.print_nodes(block, indent + 1)

    @dispatch(renpy.ast.While)
    def print_while(self, ast, indent):
        self.lines[ast.block[0].linenumber - 1] = (indent,"while %s:" % ast.condition)

        self.print_nodes(ast.block, indent + 1)

    # @dispatch(renpy.ast.Pass)
    # def print_pass(self, ast):
    #     if (self.index and
    #         isinstance(self.block[self.index - 1], renpy.ast.Call)):
    #         return

    #     if (self.index > 1 and
    #         isinstance(self.block[self.index - 2], renpy.ast.Call) and
    #         isinstance(self.block[self.index - 1], renpy.ast.Label) and
    #         self.block[self.index - 2].linenumber == ast.linenumber):
    #         return

    #     self.advance_to_line(ast.linenumber)
    #     self.indent()
    #     self.write("pass")

    def require_init(self):
        if not self.in_init:
            self.missing_init = True

    # def set_best_init_offset(self, nodes):
    #     votes = {}
    #     for ast in nodes:
    #         ast = util.convert_ast(ast)
    #         if not isinstance(ast, renpy.ast.Init):
    #             continue
    #         offset = ast.priority
    #         # Keep this block in sync with print_init
    #         if len(ast.block) == 1 and not self.should_come_before(ast, ast.block[0]):
    #             if isinstance(ast.block[0], renpy.ast.Screen):
    #                 offset -= -500
    #             elif isinstance(ast.block[0], renpy.ast.Testcase):
    #                 offset -= 500
    #             elif isinstance(ast.block[0], renpy.ast.Image):
    #                 offset -= 500 if self.is_356c6e34_or_later else 990
    #         votes[offset] = votes.get(offset, 0) + 1
    #     if votes:
    #         winner = max(votes, key=votes.get)
    #         # It's only worth setting an init offset if it would save
    #         # more than one priority specification versus not setting one.
    #         if votes.get(0, 0) + 1 < votes[winner]:
    #             self.set_init_offset(winner)

    # def set_init_offset(self, offset):
    #     def do_set_init_offset(linenumber):
    #         # if we got to the end of the file and haven't emitted this yet,
    #         # don't bother, since it only applies to stuff below it.
    #         if linenumber is None or linenumber - self.linenumber <= 1 or self.indent_level:
    #             return True
    #         if offset != self.init_offset:
    #             self.indent()
    #             self.write("init offset = %s" % offset)
    #             self.init_offset = offset
    #         return False

    #     self.do_when_blank_line(do_set_init_offset)

    # @dispatch(renpy.ast.Init)
    # def print_init(self, ast):
    #     in_init = self.in_init
    #     self.in_init = True
    #     try:
    #         # A bunch of statements can have implicit init blocks
    #         # Define has a default priority of 0, screen of -500 and image of 990
    #         # Keep this block in sync with set_best_init_offset
    #         # TODO merge this and require_init into another decorator or something
    #         if len(ast.block) == 1 and (
    #             isinstance(ast.block[0], (renpy.ast.Define,
    #                                       renpy.ast.Default,
    #                                       renpy.ast.Transform)) or
    #             (ast.priority == -500 + self.init_offset and isinstance(ast.block[0], renpy.ast.Screen)) or
    #             (ast.priority == self.init_offset and isinstance(ast.block[0], renpy.ast.Style)) or
    #             (ast.priority == 500 + self.init_offset and isinstance(ast.block[0], renpy.ast.Testcase)) or
    #             (ast.priority == 0 + self.init_offset and isinstance(ast.block[0], renpy.ast.UserStatement) and ast.block[0].line.startswith("layeredimage ")) or
    #             # Images had their default init priority changed in commit 679f9e31 (Ren'Py 6.99.10).
    #             # We don't have any way of detecting this commit, though. The closest one we can
    #             # detect is 356c6e34 (Ren'Py 6.99). For any versions in between these, we'll emit
    #             # an unnecessary "init 990 " before image statements, but this doesn't affect the AST,
    #             # and any other solution would result in incorrect code being generated in some cases.
    #             (ast.priority == (500 if self.is_356c6e34_or_later else 990) + self.init_offset and isinstance(ast.block[0], renpy.ast.Image))) and not (
    #             self.should_come_before(ast, ast.block[0])):
    #             # If they fulfill this criteria we just print the contained statement
    #             self.print_nodes(ast.block)

    #         # translatestring statements are split apart and put in an init block.
    #         elif (len(ast.block) > 0 and
    #                 ast.priority == self.init_offset and
    #                 all(isinstance(i, renpy.ast.TranslateString) for i in ast.block) and
    #                 all(i.language == ast.block[0].language for i in ast.block[1:])):
    #             self.lines[ast.linenumber] = (indent, "translate %s strings:" % ast.block[0].language or "None")
    #             self.print_nodes(ast.block, indent + 1)

    #         else:
    #             self.indent()
    #             self.write("init")
    #             if ast.priority != self.init_offset:
    #                 self.write(" %d" % (ast.priority - self.init_offset))

    #             if len(ast.block) == 1 and not self.should_come_before(ast, ast.block[0]):
    #                 self.write(" ")
    #                 self.skip_indent_until_write = True
    #                 self.print_nodes(ast.block)
    #             else:
    #                 self.write(":")
    #                 self.print_nodes(ast.block, 1)
    #     finally:
    #         self.in_init = in_init

    # def print_say_inside_menu(self):
    #     self.print_say(self.say_inside_menu, inmenu=True)
    #     self.say_inside_menu = None

    # def print_menu_item(self, label, condition, block, arguments):
    #     self.indent()
    #     self.write('"%s"' % string_escape(label))

    #     if arguments is not None:
    #         self.write(reconstruct_arginfo(arguments))

    #     if block is not None:
    #         if ((PY2 and isinstance(condition, unicode)) or (PY3 and isinstance(condition, str))) and (condition != 'True'):
    #             self.write(" if %s" % condition)
    #         self.write(":")
    #         self.print_nodes(block, 1)

    @dispatch(renpy.ast.Menu)
    def print_menu(self, ast, indent):
        self.lines[ast.linenumber] = (indent, "menu")
        if self.label_inside_menu is not None:
            self.lines[ast.linenumber][1] += " %s" % self.label_inside_menu.name
            self.label_inside_menu = None

        if hasattr(ast, "arguments") and ast.arguments is not None:
            self.lines[ast.linenumber][1] += reconstruct_arginfo(ast.arguments)

        self.lines[ast.linenumber][1] += ":"

        with self.increase_indent():
            if ast.with_ is not None:
                self.lines[ast.linenumber+1] = (indent + 1, "with %s" % ast.with_)

            if ast.set is not None:
                if self.lines.get(ast.linenumber + 1) == None:
                    self.lines[ast.linenumber+1] = (indent + 1, "set %s" % ast.set)
                else:
                    self.lines[ast.linenumber+2] = (indent + 1, "set %s" % ast.set)

            if hasattr(ast, "item_arguments"):
                item_arguments = ast.item_arguments
            else:
                item_arguments = [None] * len(ast.items)

            for (label, condition, block), arguments in zip(ast.items, item_arguments):
                if self.translator:
                    label = self.translator.strings.get(label, label)
                
                self.print_menu_item(label, condition, block, arguments)

    @dispatch(renpy.ast.Python)
    def print_python(self, ast, indent, early=False):

        code = ast.code.source
        if code[0] == '\n':
            code = code[1:]
            self.lines[ast.linenumber] = (indent, "python")
            if early:
                self.lines[ast.linenumber][1] += " early"
            if ast.hide:
                self.lines[ast.linenumber][1] += " hide"
            if hasattr(ast, "store") and ast.store != "store":
                self.lines[ast.linenumber][1] += " in "
                # Strip prepended "store."
                self.lines[ast.linenumber][1] += ast.store[6:]
            self.lines[ast.linenumber][1] += ":"

            self.write_lines(split_logical_lines(code), ast.ast.linenumber + 1)

        else:
            self.lines[ast.linenumber][1] += "$ %s" % code

    @dispatch(renpy.ast.EarlyPython)
    def print_earlypython(self, ast, indent):
        self.print_python(ast, indent, early=True)

    # @dispatch(renpy.ast.Define)
    # @dispatch(renpy.ast.Default)
    # def print_define(self, ast, indent):
    #     self.require_init()
    #     if isinstance(ast, renpy.ast.Default):
    #         name = "default"
    #     else:
    #         name = "define"

    #     # If we have an implicit init block with a non-default priority, we need to store the priority here.
    #     priority = ""
    #     if isinstance(self.parent, renpy.ast.Init):
    #         init = self.parent
    #         if init.priority != self.init_offset and len(init.block) == 1 and not self.should_come_before(init, ast):
    #             priority = " %d" % (init.priority - self.init_offset)
    #     index = ""
    #     if hasattr(ast, "index") and ast.index is not None:
    #         index = "[%s]" % ast.index.source
    #     if not hasattr(ast, "store") or ast.store == "store":
    #         self.lines[ast.linenumber] = (indent, "%s%s %s%s = %s" % (name, priority, ast.varname, index, ast.code.source))
    #     else:
    #         self.lines[ast.linenumber] = (indent, "%s%s %s.%s%s = %s" % (name, priority, ast.store[6:], ast.varname, index, ast.code.source))

    @dispatch(renpy.ast.Say)
    def print_say(self, ast, indent):
        self.lines[ast.linenumber] = (indent, say_get_code(ast))

    @dispatch(renpy.ast.UserStatement)
    def print_userstatement(self, ast, indent):
        self.lines[ast.linenumber] = (indent, ast.line)

        if hasattr(ast, "block") and ast.block:
            self.print_lex(ast.block, indent + 1)

    def print_lex(self, lex, indent):
        for file, linenumber, content, block in lex:
            self.lines[linenumber] = (indent, content)
            if block:
                    self.print_lex(block, indent + 1)

    @dispatch(renpy.ast.PostUserStatement)
    def print_postuserstatement(self, ast, indent):
        pass

    @dispatch(renpy.ast.Style)
    def print_style(self, ast, indent):
        self.require_init()
        keywords = {ast.linenumber: WordConcatenator(False, True)}

        # These don't store a line number, so just put them on the first line
        if ast.parent is not None:
            keywords[ast.linenumber].append("is %s" % ast.parent)
        if ast.clear:
            keywords[ast.linenumber].append("clear")
        if ast.take is not None:
            keywords[ast.linenumber].append("take %s" % ast.take)
        for delname in ast.delattr:
            keywords[ast.linenumber].append("del %s" % delname)

        # These do store a line number
        if ast.variant is not None:
            if ast.variant.linenumber not in keywords:
                keywords[ast.variant.linenumber] = WordConcatenator(False)
            keywords[ast.variant.linenumber].append("variant %s" % ast.variant)
        for key, value in ast.properties.items():
            if value.linenumber not in keywords:
                keywords[value.linenumber] = WordConcatenator(False)
            keywords[value.linenumber].append("%s %s" % (key, value))

        keywords = sorted([(k, v.join()) for k, v in keywords.items()],
                          key=itemgetter(0))
        
        self.lines[ast.linenumber] = (indent, "style %s" % ast.style_name)
        if keywords[0][1]:
            self.lines[ast.linenumber][1] += " %s" % keywords[0][1]
        if len(keywords) > 1:
            self.lines[ast.linenumber][1] += ":"
            for i in keywords[1:]:
                self.lines[i[0]] = (indent + 1,i[1])

    @dispatch(renpy.ast.Translate)
    def print_translate(self, ast, indent):
        self.lines[ast.loc[1]] = (indent, "translate %s %s:" % (ast.language or "None", ast.identifier))

        self.print_nodes(ast.block, indent + 1)

    @dispatch(renpy.ast.EndTranslate)
    def print_endtranslate(self, ast, indent):
        # an implicitly added node which does nothing...
        pass

    @dispatch(renpy.ast.TranslateString)
    def print_translatestring(self, ast, indent):
        self.require_init()

        # TranslateString's linenumber refers to the line with "old", not to the
        # line with "translate %s strings:"
        with self.increase_indent():
            self.advance_to_line(ast.linenumber)
            self.indent()
            self.lines[ast.linenumber] = (indent, 'old "%s"' % string_escape(ast.old))
            if hasattr(ast, 'newloc'):
                self.lines[ast.newloc[1]] = (indent, 'new "%s"' % string_escape(ast.new))
            else:
                self.lines[ast.linenumber + 1] = (indent, 'new "%s"' % string_escape(ast.new))

    @dispatch(renpy.ast.TranslateBlock)
    @dispatch(renpy.ast.TranslateEarlyBlock)
    def print_translateblock(self, ast, indent):
        self.indent()
        self.lines[ast.loc[1]] = (indent, "translate %s " % (ast.language or "None"))

        in_init = self.in_init
        if len(ast.block) == 1 and isinstance(ast.block[0], (renpy.ast.Python, renpy.ast.Style)):
            # Ren'Py counts the TranslateBlock from "translate python" and "translate style" as an Init.
            self.in_init = True
        try:
            self.print_nodes(ast.block, indent + 1)
        finally:
            self.in_init = in_init

    # @dispatch(renpy.ast.Screen)
    # def print_screen(self, ast, indent):
    #     self.require_init()
    #     screen = ast.screen
    #     if isinstance(screen, renpy.screenlang.ScreenLangScreen):
    #         self.linenumber = screendecompiler.pprint(self.out_file, screen, self.indent_level,
    #                                 self.linenumber,
    #                                 self.decompile_python,
    #                                 self.skip_indent_until_write,
    #                                 self.printlock)
    #         self.skip_indent_until_write = False

    #     elif isinstance(screen, renpy.sl2.slast.SLScreen):
    #         def print_atl_callback(linenumber, indent_level, atl):
    #             self.skip_indent_until_write = False
    #             old_linenumber = self.linenumber
    #             self.linenumber = linenumber
    #             with self.increase_indent(indent_level - self.indent_level):
    #                 self.print_atl(atl)
    #             new_linenumber = self.linenumber
    #             self.linenumber = old_linenumber
    #             return new_linenumber

    #         self.linenumber = sl2decompiler.pprint(self.out_file, screen, print_atl_callback,
    #                                 self.indent_level,
    #                                 self.linenumber,
    #                                 self.skip_indent_until_write,
    #                                 self.printlock,
    #                                 self.tag_outside_block)
    #         self.skip_indent_until_write = False
    #     else:
    #         self.print_unknown(screen)

    # @dispatch(renpy.ast.Testcase)
    # def print_testcase(self, ast, indent):
    #     self.require_init()
    #     self.lines[ast.loc[1]] = (indent, 'testcase %s:' % ast.label)
    #     self.linenumber = testcasedecompiler.pprint(self.out_file, ast.test.block, self.indent_level + 1,
    #                             self.linenumber,
    #                             self.skip_indent_until_write,
    #                             self.printlock)
    #     self.skip_indent_until_write = False

    @dispatch(renpy.ast.RPY)
    def print_RPY(self, ast, indent):
        self.lines[ast.loc[1]] = (indent, "rpy {} {}".format(ast.rest[0], ast.rest[1]))

    @dispatch(renpy.ast.Camera)
    def print_Camera(self, ast, indent):
        self.lines[ast.linenumber] = (indent, "camera " + ast.layer)
        if ast.at_list != []:
            self.lines[ast.linenumber][1] += " at " + ast.at_list[0]
        if ast.atl is not None:
            self.lines[ast.linenumber][1] += ":"
            self.print_atl(ast.atl, indent + 1)