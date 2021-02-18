#	pysuchsel - Create Suchsel word puzzles from Python
#	Copyright (C) 2019-2019 Johannes Bauer
#
#	This file is part of pysuchsel.
#
#	pysuchsel is free software; you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation; this program is ONLY licensed under
#	version 3 of the License, later versions are explicitly excluded.
#
#	pysuchsel is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	You should have received a copy of the GNU General Public License
#	along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#	Johannes Bauer <JohannesBauer@gmx.de>

import random
import collections
from SVGDocument import SVGDocument
import pylightxl as xl
import os

class VoidPlaceholder():
	def __eq__(self, other):
		return other.__class__ == self.__class__

	def __neq__(self, other):
		return not (self == other)

	def __str__(self):
		return "."

class ArrowMarker():
	def __init__(self, marking, direction):
		self._marking = marking
		self._direction = direction

	@property
	def marking(self):
		return self._marking

	def __str__(self):
		return {
			"left":		"<",
			"right":	">",
			"down":		"v",
		}.get(self._direction, "?")

DIRECTIONS = dict(
	lr=lambda x, y: (x + 1, y),
	rl=lambda x, y: (x - 1, y),
	tb=lambda x, y: (x, y - 1),
	bt=lambda x, y: (x, y + 1),
	dbr=lambda x, y: (x + 1, y - 1),
	dbl=lambda x, y: (x - 1, y - 1),
	dtr=lambda x, y: (x + 1, y + 1),
	dtl=lambda x, y: (x - 1, y + 1)
)

class Suchsel():
	def __init__(self, width, height, placement, attempts, verbose=0, print_word=None):
		self._width = width
		self._height = height
		self._placement = placement
		self._attempts = attempts
		self._grid = { }
		self._words = []
		self._rules = dict()
		self._verbose = verbose
		self.print_word = print_word

	def _rulerange(self, origin_x, origin_y, rulename):
		(x, y) = (origin_x, origin_y)
		while True:
			yield (x, y)
			if rulename == "lr":
				x += 1
			elif rulename == "tb":
				y += 1
			elif rulename == "dbr":
				x += 1
				y += 1
			elif rulename == "dbl":
				x -= 1
				y += 1
			elif rulename == "dtr":
				x += 1
				y -= 1
			elif rulename == "dtl":
				x -= 1
				y -= 1
			else:
				raise NotImplementedError(rulename)

	def _adjacent_fields(self, x, y, rulename):
		if rulename in [ "tb", "bt" ]:
			yield (x - 1, y)
			yield (x + 1, y)
		elif rulename in [ "lr", "rl" ]:
			yield (x, y - 1)
			yield (x, y + 1)
		else:
			raise NotImplementedError(rulename)

	def _find_rule(self, word, crossword_marker = None):
		rule = self._placement.event()
		if crossword_marker is not None:
			direction = {
				"lr":	"right",
				"rl":	"left",
				"tb":	"down",
				"bt":	"up",
				"dbr":	"down-right",
				"dbl":	"down-left",
				"dtr":	"up-right",
				"dtl":	"up-left",
			}[rule]
			arrow_marker = ArrowMarker(marking = crossword_marker, direction = direction)
			word = [ arrow_marker ] + list(word) + [ VoidPlaceholder() ]

		if rule in [ "lr", "rl" ]:
			req_width = len(word)
			req_height = 1
		elif rule in [ "tb", "bt" ]:
			req_width = 1
			req_height = len(word)
		elif rule in [ "dbr", "dtl", "dtr", "dbl" ]:
			req_width = len(word)
			req_height = len(word)
		else:
			raise NotImplementedError(rule)

		if rule in [ "rl", "bt" ]:
			word = list(reversed(word))
			if rule == "rl":
				rule = "lr"
			elif rule == "bt":
				rule = "tb"
		return (word, rule, req_width, req_height)

	def _attempt_place(self, word, must_be_contiguous = False, crossword_marker = None):
		(word, rule, req_width, req_height) = self._find_rule(word, crossword_marker = crossword_marker)

		max_x = self._width - req_width
		max_y = self._height - req_height
		if (max_x < 0) or (max_y < 0):
			# Word does not fit with this rule, abort.
			return False

		src_x = random.randint(0, max_x)
		src_y = random.randint(0, max_y)

		if rule in [ "dtl", "dbl" ]:
			src_x += len(word) - 1
		if rule in [ "dtr", "dtl" ]:
			src_y += len(word) - 1

		contiguous_letters = 0
		for (want_place, (x, y)) in zip(word, self._rulerange(src_x, src_y, rule)):
			present = self._grid.get((x, y))
			if (present == want_place) and isinstance(present, str):
				# We count overlapping letters, but not overlapping
				# VoidPlacerholders
				contiguous_letters += 1
			if (present is not None) and (present != want_place):
				# Letter already occupied with different letter than we would
				# like there
				return False

			if (present is None) and (crossword_marker is not None):
				# Field is empty, check adjacent fields for emptyness if this
				# is a crossword
				for (adjx, adjy) in self._adjacent_fields(x, y, rule):
					adjacent_content = self._grid.get((adjx, adjy))
					if (adjacent_content is not None) and not isinstance(adjacent_content, VoidPlaceholder):
						# There's a letter or arrowfield in there, that's
						# forbidden
						return False

		if must_be_contiguous and (contiguous_letters == 0):
			return False

		# All letters fit!
		for (want_place, (x, y)) in zip(word, self._rulerange(src_x, src_y, rule)):
			self._grid[(x, y)] = want_place

		# Track used rules
		if rule not in self._rules:
			self._rules[rule] = 0
		self._rules[rule] += 1

		if self._verbose > 1:
			self.dump()

		return True

	def _place(self, word, contiguous = False):
		# First try contiguous placement
		if contiguous and (len(self._grid) > 0):
			for i in range(self._attempts):
				if self._attempt_place(word, must_be_contiguous = True):
					return True
		for i in range(self._attempts):
			if self._attempt_place(word):
				return True
		return False

	def place(self, word, contiguous = False):
		self._grid_previous = self._grid

		if self.is_substring(word):
			if self._verbose > 0:
				print ("Won't place:", word, " because is substring.")
			return False

		if not self._place(word, contiguous):
			return False

		if self.is_coocurence(word):
			# rollback
			if self._verbose > 0:
				print ('found cooccurence! grid rollback...')
			self._grid = self._grid_previous
			return False

		self._words.append(word)

		return True

	def place_crossword(self, word, crossword_marker):
		contiguous = (len(self._grid) > 0)
		for i in range(self._attempts):
			if self._attempt_place(word, must_be_contiguous = contiguous, crossword_marker = crossword_marker):
				return True
		return False

	@property
	def void(self):
		spaces = self._height * self._width
		return (spaces - len(self._grid))
	
	def hide_word(self, word):
		if self.void == len(word):
			if self._verbose > 0:
				print ('Can hide', word)
			return True
		else:
			return False

	def can_hide(self):
		hidden_size = random.randrange(5,12)
		if self.void <= hidden_size:
			if self._verbose > 0:
				print ('Will hide a word of length', self.void, hidden_size)
			return hidden_size

	def is_substring(self, word):
		for placed in self._words:
			if word in placed:
				return True
		return False

	def is_coocurence(self, word):
		count = 0
		for x, y in self._letters_idx[word[0]]:
			for rule in DIRECTIONS.keys():
				if self.search(word[1:], x, y, rule):
					count += 1

		return count > 1

	def search(self, part, x, y, rule):
		letter, remaining = part[0], part[1:]
		if not remaining:
			return True

		pos = DIRECTIONS[rule](x, y)
		if pos in self._grid and self._grid[pos] == letter:
			x, y = pos
			return self.search(remaining, x, y, rule)

	@property
	def _letters_idx(self):
		_ = dict()
		for pos, letter in self._grid.items():
			if letter not in _:
				_[letter] = []
			_[letter].append(pos)
		return _

	def fill(self, filler):
		for y in range(self._height):
			for x in range(self._width):
				pos = (x, y)
				if pos not in self._grid:
					self._grid[pos] = filler.get()

	def dump(self):
		from pprint import pprint
		print ('\n'.join(self._words))
		print ("  " + ("0123456789" * 10)[:self._width])
		for y in range(self._height):
			line = [ ]
			for x in range(self._width):
				letter = self._grid.get((x, y), " ")
				line.append(str(letter))
			print(f'{y:02}' + ("".join(line)))
		

	def write_svg(self, output_filename, place_letters = True):
		svg = SVGDocument()
		size = 20
		for y in range(self._height):
			for x in range(self._width):
				pos = (x, y)
				letter = self._grid.get(pos)
				if isinstance(letter, str):
					svg.rect(size * x, size * y, size, size)
					if place_letters:
						svg.textregion(size * x, size * y + 4, size, size, letter, halign = "center")
				elif isinstance(letter, ArrowMarker):
					svg.rect(size * x, size * y, size, size, strokecolor = "3498db")
					svg.textregion(size * x, size * y + 4, size, size, str(letter.marking), halign = "center")

		svg.autosize()
		with open(output_filename, "w") as f:
			svg.write(f)


	def write_xls(self, solution, outfile=None, metafile=False):
		size_x, size_y = (self._height, self._width)
		words = self._words

		if not outfile:
			basename = f'mots-caches-{size_x}-{size_y}-{len(words):03}-{solution}'
		else:
			basename = outfile

		words = sorted(words)

		##########
		# game
		db = xl.Database()
		db.add_ws(ws="jeu")
		for col in range(self._width):
			for row in range(self._height):
				pos = (col, row)
				letter = self._grid.get(pos)
				db.ws(ws='jeu').update_index(row=row+1, col=col+1, val=letter)

		##########
		# words
		if metafile:
			fh_mots = open(f'{basename}-mots.txt', 'w')
			fh_mots.write(f'Mot de {len(solution)} lettres.\n')
		else:
			db.add_ws(ws="mots")		

		letter = None
		col = 0
		for word in words:
			if word[0] != letter:
				col += 1
				letter = word[0]
				row = 2
				if metafile:
					fh_mots.write(f'{letter}\n')
				else:
					db.ws(ws='mots').update_index(row=row, col=col, val=letter)			
				print (row, letter)

			row += 1
			print (11, row, word)
			if metafile:
				fh_mots.write(f'{self.print_word(word)}\n')
			else:
				db.ws(ws='mots').update_index(row=row, col=col, val=self.print_word(word))


		if metafile:
			fh_mots.close()

		##########
		# solution
		if metafile:
			fh_solution = open(f'{basename}-solution.txt', 'w')
			fh_solution.write(self.print_word(solution))
			fh_solution.close()
		else:
			db.add_ws(ws="solution")
			db.ws(ws='solution').update_index(row=1, col=1, val=f'Mot de {len(solution)} lettres.')
			db.ws(ws='solution').update_index(row=2, col=1, val=self.print_word(solution))

		xl.writexl(db=db, fn=f'{basename}.xls')
