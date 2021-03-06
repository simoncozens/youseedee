#!/usr/bin/env python3
# flake8: noqa: F821

"""usage: ./gen-use-table.py IndicSyllabicCategory.txt IndicPositionalCategory.txt UnicodeData.txt ArabicShaping.txt Blocks.txt IndicSyllabicCategory-Additional.txt IndicPositionalCategory-Additional.txt

Input files:
* https://unicode.org/Public/UCD/latest/ucd/IndicSyllabicCategory.txt
* https://unicode.org/Public/UCD/latest/ucd/IndicPositionalCategory.txt
* https://unicode.org/Public/UCD/latest/ucd/UnicodeData.txt
* https://unicode.org/Public/UCD/latest/ucd/ArabicShaping.txt
* https://unicode.org/Public/UCD/latest/ucd/Blocks.txt
* ms-use/IndicPositionalCategory-Additional.txt
* ms-use/IndicSyllabicCategory-Additional.txt
"""

import sys

if len (sys.argv) != 8:
	sys.exit (__doc__)

BLACKLISTED_BLOCKS = [
	'Samaritan',
	'Thai',
	'Lao',
]

files = [open (x, encoding='utf-8') for x in sys.argv[1:]]

headers = [[f.readline () for i in range (2)] for j,f in enumerate(files) if j != 2]
for j in range(5, 7):
	for line in files[j]:
		line = line.rstrip()
		if not line:
			break
		headers[j - 1].append(line)
headers.append (["UnicodeData.txt does not have a header."])

data = [{} for _ in files]
values = [{} for _ in files]
for i, f in enumerate (files):
	for line in f:

		j = line.find ('#')
		if j >= 0:
			line = line[:j]

		fields = [x.strip () for x in line.split (';')]
		if len (fields) == 1:
			continue

		uu = fields[0].split ('..')
		start = int (uu[0], 16)
		if len (uu) == 1:
			end = start
		else:
			end = int (uu[1], 16)

		t = fields[1 if i not in [2, 3] else 2]

		if i == 3:
			t = 'jt_' + t
		elif i == 5 and t == 'Consonant_Final_Modifier':
			# TODO: https://github.com/MicrosoftDocs/typography-issues/issues/336
			t = 'Syllable_Modifier'
		elif i == 6 and t == 'NA':
			t = 'Not_Applicable'

		i0 = i if i < 5 else i - 5
		for u in range (start, end + 1):
			data[i0][u] = t
		values[i0][t] = values[i0].get (t, 0) + end - start + 1

defaults = ('Other', 'Not_Applicable', 'Cn', 'jt_X', 'No_Block')

# TODO Characters that are not in Unicode Indic files, but used in USE
data[0][0x0640] = defaults[0]
data[0][0x1B61] = defaults[0]
data[0][0x1B63] = defaults[0]
data[0][0x1B64] = defaults[0]
data[0][0x1B65] = defaults[0]
data[0][0x1B66] = defaults[0]
data[0][0x1B67] = defaults[0]
data[0][0x1B69] = defaults[0]
data[0][0x1B6A] = defaults[0]
data[0][0x2060] = defaults[0]
for u in range (0x07CA, 0x07EA + 1):
	data[0][u] = defaults[0]
data[0][0x07FA] = defaults[0]
for u in range (0x0840, 0x0858 + 1):
	data[0][u] = defaults[0]
for u in range (0x1887, 0x18A8 + 1):
	data[0][u] = defaults[0]
data[0][0x18AA] = defaults[0]
for u in range (0xA840, 0xA872 + 1):
	data[0][u] = defaults[0]
for u in range (0x10B80, 0x10B91 + 1):
	data[0][u] = defaults[0]
for u in range (0x10BA9, 0x10BAE + 1):
	data[0][u] = defaults[0]
data[0][0x10FB0] = defaults[0]
for u in range (0x10FB2, 0x10FB6 + 1):
	data[0][u] = defaults[0]
for u in range (0x10FB8, 0x10FBF + 1):
	data[0][u] = defaults[0]
for u in range (0x10FC1, 0x10FC4 + 1):
	data[0][u] = defaults[0]
for u in range (0x10FC9, 0x10FCB + 1):
	data[0][u] = defaults[0]
# TODO https://github.com/harfbuzz/harfbuzz/pull/1685
data[0][0x1B5B] = 'Consonant_Placeholder'
data[0][0x1B5C] = 'Consonant_Placeholder'
data[0][0x1B5F] = 'Consonant_Placeholder'
data[0][0x1B62] = 'Consonant_Placeholder'
data[0][0x1B68] = 'Consonant_Placeholder'
# TODO https://github.com/harfbuzz/harfbuzz/issues/1035
data[0][0x11C44] = 'Consonant_Placeholder'
data[0][0x11C45] = 'Consonant_Placeholder'
# TODO https://github.com/harfbuzz/harfbuzz/pull/1399
data[0][0x111C8] = 'Consonant_Placeholder'

# Merge data into one dict:
for i,v in enumerate (defaults):
	values[i][v] = values[i].get (v, 0) + 1
combined = {}
for i,d in enumerate (data):
	for u,v in d.items ():
		if i >= 2 and not u in combined:
			continue
		if not u in combined:
			combined[u] = list (defaults)
		combined[u][i] = v
combined = {k:v for k,v in combined.items() if v[4] not in BLACKLISTED_BLOCKS}
data = combined
del combined


property_names = [
	# General_Category
	'Cc', 'Cf', 'Cn', 'Co', 'Cs', 'Ll', 'Lm', 'Lo', 'Lt', 'Lu', 'Mc',
	'Me', 'Mn', 'Nd', 'Nl', 'No', 'Pc', 'Pd', 'Pe', 'Pf', 'Pi', 'Po',
	'Ps', 'Sc', 'Sk', 'Sm', 'So', 'Zl', 'Zp', 'Zs',
	# Indic_Syllabic_Category
	'Other',
	'Bindu',
	'Visarga',
	'Avagraha',
	'Nukta',
	'Virama',
	'Pure_Killer',
	'Invisible_Stacker',
	'Vowel_Independent',
	'Vowel_Dependent',
	'Vowel',
	'Consonant_Placeholder',
	'Consonant',
	'Consonant_Dead',
	'Consonant_With_Stacker',
	'Consonant_Prefixed',
	'Consonant_Preceding_Repha',
	'Consonant_Succeeding_Repha',
	'Consonant_Subjoined',
	'Consonant_Medial',
	'Consonant_Final',
	'Consonant_Head_Letter',
	'Consonant_Initial_Postfixed',
	'Modifying_Letter',
	'Tone_Letter',
	'Tone_Mark',
	'Gemination_Mark',
	'Cantillation_Mark',
	'Register_Shifter',
	'Syllable_Modifier',
	'Consonant_Killer',
	'Non_Joiner',
	'Joiner',
	'Number_Joiner',
	'Number',
	'Brahmi_Joining_Number',
	# Indic_Positional_Category
	'Not_Applicable',
	'Right',
	'Left',
	'Visual_Order_Left',
	'Left_And_Right',
	'Top',
	'Bottom',
	'Top_And_Bottom',
	'Top_And_Bottom_And_Left',
	'Top_And_Right',
	'Top_And_Left',
	'Top_And_Left_And_Right',
	'Bottom_And_Left',
	'Bottom_And_Right',
	'Top_And_Bottom_And_Right',
	'Overstruck',
	# Joining_Type
	'jt_C',
	'jt_D',
	'jt_L',
	'jt_R',
	'jt_T',
	'jt_U',
	'jt_X',
]

class PropertyValue(object):
	def __init__(self, name_):
		self.name = name_
	def __str__(self):
		return self.name
	def __eq__(self, other):
		return self.name == (other if isinstance(other, str) else other.name)
	def __ne__(self, other):
		return not (self == other)
	def __hash__(self):
		return hash(str(self))

property_values = {}

for name in property_names:
	value = PropertyValue(name)
	assert value not in property_values
	assert value not in globals()
	property_values[name] = value
globals().update(property_values)


def is_BASE(U, UISC, UGC, AJT):
	return (UISC in [Number, Consonant, Consonant_Head_Letter,
			Tone_Letter,
			Vowel_Independent,
			] or
		# TODO: https://github.com/MicrosoftDocs/typography-issues/issues/484
		AJT in [jt_C, jt_D, jt_L, jt_R] and not is_ZWJ(U, UISC, UGC, AJT) or
		(UGC == Lo and UISC in [Avagraha, Bindu, Consonant_Final, Consonant_Medial,
					Consonant_Subjoined, Vowel, Vowel_Dependent]))
def is_BASE_IND(U, UISC, UGC, AJT):
	return (UISC in [Consonant_Dead, Modifying_Letter] or
		(UGC == Po and not U in [0x0F04, 0x0F05, 0x0F06, 0x104B, 0x104E, 0x1800, 0x1807, 0x180A, 0x1B5B, 0x1B5C, 0x1B5F, 0x2022, 0x111C8, 0x11A3F, 0x11A45, 0x11C44, 0x11C45]))
def is_BASE_NUM(U, UISC, UGC, AJT):
	return UISC == Brahmi_Joining_Number
def is_BASE_OTHER(U, UISC, UGC, AJT):
	if UISC == Consonant_Placeholder: return True
	return U in [0x2015, 0x2022, 0x25FB, 0x25FC, 0x25FD, 0x25FE]
def is_CONS_FINAL(U, UISC, UGC, AJT):
	return ((UISC == Consonant_Final and UGC != Lo) or
		UISC == Consonant_Succeeding_Repha)
def is_CONS_FINAL_MOD(U, UISC, UGC, AJT):
	return UISC == Syllable_Modifier
def is_CONS_MED(U, UISC, UGC, AJT):
	# Consonant_Initial_Postfixed is new in Unicode 11; not in the spec.
	return (UISC == Consonant_Medial and UGC != Lo or
		UISC == Consonant_Initial_Postfixed)
def is_CONS_MOD(U, UISC, UGC, AJT):
	return (UISC in [Nukta, Gemination_Mark, Consonant_Killer] and
		not is_SYM_MOD(U, UISC, UGC, AJT))
def is_CONS_SUB(U, UISC, UGC, AJT):
	return UISC == Consonant_Subjoined and UGC != Lo
def is_CONS_WITH_STACKER(U, UISC, UGC, AJT):
	return UISC == Consonant_With_Stacker
def is_HALANT(U, UISC, UGC, AJT):
	return (UISC in [Virama, Invisible_Stacker]
		and not is_HALANT_OR_VOWEL_MODIFIER(U, UISC, UGC, AJT)
		and not is_SAKOT(U, UISC, UGC, AJT))
def is_HALANT_OR_VOWEL_MODIFIER(U, UISC, UGC, AJT):
	# https://github.com/harfbuzz/harfbuzz/issues/1102
	# https://github.com/harfbuzz/harfbuzz/issues/1379
	return U in [0x11046, 0x1134D]
def is_HALANT_NUM(U, UISC, UGC, AJT):
	return UISC == Number_Joiner
def is_ZWNJ(U, UISC, UGC, AJT):
	return UISC == Non_Joiner
def is_ZWJ(U, UISC, UGC, AJT):
	return UISC == Joiner
def is_Word_Joiner(U, UISC, UGC, AJT):
	return U == 0x2060
def is_OTHER(U, UISC, UGC, AJT):
	return (UISC == Other
		and not is_BASE(U, UISC, UGC, AJT)
		and not is_SYM(U, UISC, UGC, AJT)
		and not is_SYM_MOD(U, UISC, UGC, AJT)
		and not is_Word_Joiner(U, UISC, UGC, AJT)
	)
def is_Reserved(U, UISC, UGC, AJT):
	return UGC == 'Cn'
def is_REPHA(U, UISC, UGC, AJT):
	return UISC in [Consonant_Preceding_Repha, Consonant_Prefixed]
def is_SAKOT(U, UISC, UGC, AJT):
	return U == 0x1A60
def is_SYM(U, UISC, UGC, AJT):
	if U in [0x25CC, 0x1E14F]: return False
	return UGC in [So, Sc] and U not in [0x0F01, 0x1B62, 0x1B68]
def is_SYM_MOD(U, UISC, UGC, AJT):
	return U in [0x1B6B, 0x1B6C, 0x1B6D, 0x1B6E, 0x1B6F, 0x1B70, 0x1B71, 0x1B72, 0x1B73]
def is_VOWEL(U, UISC, UGC, AJT):
	# https://github.com/harfbuzz/harfbuzz/issues/376
	return (UISC == Pure_Killer or
		(UGC != Lo and UISC in [Vowel, Vowel_Dependent] and U not in [0xAA29]))
def is_VOWEL_MOD(U, UISC, UGC, AJT):
	# https://github.com/harfbuzz/harfbuzz/issues/376
	return (UISC in [Tone_Mark, Cantillation_Mark, Register_Shifter, Visarga] or
		(UGC != Lo and (UISC == Bindu or U in [0xAA29])))

# CGJ and VS are handled in find_syllables
use_mapping = {
	'B':	is_BASE,
	'IND':	is_BASE_IND,
	'N':	is_BASE_NUM,
	'GB':	is_BASE_OTHER,
	'F':	is_CONS_FINAL,
	'FM':	is_CONS_FINAL_MOD,
	'M':	is_CONS_MED,
	'CM':	is_CONS_MOD,
	'SUB':	is_CONS_SUB,
	'CS':	is_CONS_WITH_STACKER,
	'H':	is_HALANT,
	'HVM':	is_HALANT_OR_VOWEL_MODIFIER,
	'HN':	is_HALANT_NUM,
	'ZWNJ':	is_ZWNJ,
	'ZWJ':	is_ZWJ,
	'WJ':	is_Word_Joiner,
	'O':	is_OTHER,
	'Rsv':	is_Reserved,
	'R':	is_REPHA,
	'S':	is_SYM,
	'Sk':	is_SAKOT,
	'SM':	is_SYM_MOD,
	'V':	is_VOWEL,
	'VM':	is_VOWEL_MOD,
}

use_positions = {
	'F': {
		'Abv': [Top],
		'Blw': [Bottom],
		'Pst': [Right],
	},
	'M': {
		'Abv': [Top],
		'Blw': [Bottom, Bottom_And_Left, Bottom_And_Right],
		'Pst': [Right],
		'Pre': [Left, Top_And_Bottom_And_Left],
	},
	'CM': {
		'Abv': [Top],
		'Blw': [Bottom, Overstruck],
	},
	'V': {
		'Abv': [Top, Top_And_Bottom, Top_And_Bottom_And_Right, Top_And_Right],
		'Blw': [Bottom, Overstruck, Bottom_And_Right],
		'Pst': [Right],
		'Pre': [Left, Top_And_Left, Top_And_Left_And_Right, Left_And_Right],
	},
	'VM': {
		'Abv': [Top],
		'Blw': [Bottom, Overstruck],
		'Pst': [Right],
		'Pre': [Left],
	},
	'SM': {
		'Abv': [Top],
		'Blw': [Bottom],
	},
	'H': None,
	'HVM': None,
	'B': None,
	'FM': {
		'Abv': [Top],
		'Blw': [Bottom],
		'Pst': [Not_Applicable],
	},
	'R': None,
	'SUB': None,
}

def map_to_use(data):
	out = {}
	items = use_mapping.items()
	for U,(UISC,UIPC,UGC,AJT,UBlock) in data.items():

		if UGC == Cn: continue

		# TODO: These variation selectors are overridden to IND, but we want to ignore them
		if U in range (0xFE00, 0xFE0F + 1): continue

		# Resolve Indic_Syllabic_Category

		# TODO: These don't have UISC assigned in Unicode 13.0.0, but have UIPC
		if 0x1CE2 <= U <= 0x1CE8: UISC = Cantillation_Mark

		# Tibetan:
		# TODO: These don't have UISC assigned in Unicode 13.0.0, but have UIPC
		if 0x0F18 <= U <= 0x0F19 or 0x0F3E <= U <= 0x0F3F: UISC = Vowel_Dependent

		# TODO: https://github.com/harfbuzz/harfbuzz/pull/627
		if 0x1BF2 <= U <= 0x1BF3: UISC = Nukta; UIPC = Bottom

		# TODO: U+1CED should only be allowed after some of
		# the nasalization marks, maybe only for U+1CE9..U+1CF1.
		if U == 0x1CED: UISC = Tone_Mark

		# TODO: https://github.com/microsoft/font-tools/issues/1
		if U == 0xA982: UISC = Consonant_Succeeding_Repha

		values = [k for k,v in items if v(U,UISC,UGC,AJT)]
		assert len(values) == 1, "%s %s %s %s %s" % (hex(U), UISC, UGC, AJT, values)
		USE = values[0]

		# Resolve Indic_Positional_Category

		# TODO: These should die, but have UIPC in Unicode 13.0.0
		if U in [0x953, 0x954]: UIPC = Not_Applicable

		# TODO: These are not in USE's override list that we have, nor are they in Unicode 13.0.0
		if 0xA926 <= U <= 0xA92A: UIPC = Top
		# TODO: https://github.com/harfbuzz/harfbuzz/pull/1037
		#  and https://github.com/harfbuzz/harfbuzz/issues/1631
		if U in [0x11302, 0x11303, 0x114C1]: UIPC = Top
		if 0x1CF8 <= U <= 0x1CF9: UIPC = Top

		# TODO: https://github.com/harfbuzz/harfbuzz/pull/982
		# also  https://github.com/harfbuzz/harfbuzz/issues/1012
		if 0x1112A <= U <= 0x1112B: UIPC = Top
		if 0x11131 <= U <= 0x11132: UIPC = Top

		assert (UIPC in [Not_Applicable, Visual_Order_Left] or U == 0x0F7F or
			USE in use_positions), "%s %s %s %s %s %s" % (hex(U), UIPC, USE, UISC, UGC, AJT)

		pos_mapping = use_positions.get(USE, None)
		if pos_mapping:
			values = [k for k,v in pos_mapping.items() if v and UIPC in v]
			assert len(values) == 1, "%s %s %s %s %s %s %s" % (hex(U), UIPC, USE, UISC, UGC, AJT, values)
			USE = USE + values[0]

		out[U] = (USE, UBlock)
	return out

defaults = ('O', 'No_Block')
data = map_to_use(data)
for k,v in data.items():
	data[k] = data[k][0]

def emit_range(end):
	print(' (0x%04x,0x%04x, "%s"), ' % (last_start[0],end,last_start[1]))

data = sorted(data.items())
last_start = data[0]
last_end = last_start[0]
for k,v in data[1:]:
	if v != last_start[1]:
		emit_range(last_end)
		last_start = (k,v)
	last_end = k
emit_range(last_end)

