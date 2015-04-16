from collections import defaultdict

from minime.util.dogma import *
from minime.util.mass import *
from minime.util import mu
from minime.core.MEReactions import *


class ProcessData(object):
    """Generic class for holding information about a process

    ME reactions are built from information in these objects

    """

    def __init__(self, id, model):
        self.id = id
        self._model = model
        # parents need to be updated every time the process is updated
        # a parent must have an update method
        self._parent_reactions = set()

    @property
    def model(self):
        return self._model

    @property
    def parent_reactions(self):
        return {self._model.reactions.get_by_id(i)
                for i in self._parent_reactions}

    def _update_parent_reactions(self):
        reactions = self._model.reactions
        for i in self._parent_reactions:
            reactions.get_by_id(i).update()

    def __repr__(self):
        return "<%s %s at 0x%x>" % (self.__class__.__name__, self.id, id(self))


class StoichiometricData(ProcessData):
    """Encodes the stoichiometry  for a reaction.

    Used by Metabolic Reactions
    """
    def __init__(self, id, model):
        ProcessData.__init__(self, id, model)
        model.stoichiometric_data.append(self)
        self._stoichiometry = {}

    @property
    def stoichiometry(self):
        return self._stoichiometry


class ModificationData(ProcessData):
    def __init__(self, id, model):
        ProcessData.__init__(self, id, model)
        model.modification_data.append(self)
        self.stoichiometry = {}
        self.enzyme = None
        self.modification_keff = None

    def get_complex_data(self):
        for i in self._model.complex_data:
            if self.id in i.modifications:
                yield i


class ComplexData(ProcessData):

    @property
    def formation(self):
        """a read-only link to the formation reaction"""
        try:
            return self._model.reactions.get_by_id("formation_" + self.id)
        except KeyError:
            return None

    @property
    def complex(self):
        """a read-only link to the complex object"""
        return self._model.metabolites.get_by_id(self.complex_id)

    @property
    def complex_id(self):
        return self.id if self._complex_id is None else self._complex_id

    @complex_id.setter
    def complex_id(self, value):
        self._complex_id = None if value == self.id else value

    def __init__(self, id, model):
        ProcessData.__init__(self, id, model)
        model.complex_data.append(self)
        # {Component.id: stoichiometry}
        self.stoichiometry = {}
        self.translocation = {}
        self.chaperones = {}
        # {ModificationData.id : number}
        self.modifications = {}
        self._complex_id = None  # assumed to be the same as id if None

    def create_complex_formation(self):
        """creates a complex formation reaction

        This assumes none exists already. Will create a reaction (prefixed by
        'formation_') which forms the complex"""
        formation_id = "formation_" + self.id
        if formation_id in self._model.reactions:
            raise ValueError("reaction %s already in model" % formation_id)
        formation = ComplexFormation(formation_id)
        formation._complex_id = self.complex_id
        self._model.add_reaction(formation)
        formation.update()


class TranscriptionData(ProcessData):
    def __init__(self, id, model, RNA_products=set()):
        ProcessData.__init__(self, id, model)
        model.transcription_data.append(self)
        self.nucleotide_sequence = ''
        self.RNA_products = RNA_products

    @property
    def nucleotide_count(self):
        return {transcription_table[i]: self.nucleotide_sequence.count(i)
                for i in ["A", "T", "G", "C"]}

    @property
    def mass(self):
        return compute_RNA_mass(self.nucleotide_count)


class TranslationData(ProcessData):
    protein_per_mRNA = 50000000
    amino_acid_sequence = ""
    mRNA = None

    def __init__(self, id, model, mRNA, protein):
        ProcessData.__init__(self, id, model)
        model.translation_data.append(self)
        self.mRNA = mRNA
        self.protein = protein

    def compute_sequence_from_DNA(self, dna_sequence):
        codons = (dna_sequence[i: i + 3]
                  for i in range(0, (len(dna_sequence)), 3))
        self.amino_acid_sequence = ''.join(codon_table[i] for i in codons)
        self.amino_acid_sequence = self.amino_acid_sequence.rstrip("*")

    @property
    def amino_acid_count(self):
        """count of each amino acid in the protein"""
        aa_count = defaultdict(lambda: 0)
        for i in self.amino_acid_sequence:
            aa_count[amino_acids[i]] += 1
        return aa_count

    @property
    def mass(self):
        """mass in kDa"""
        return compute_protein_mass(self.amino_acid_count)


class tRNAData(ProcessData):
    synthetase = None
    synthetase_keff = 65.

    def __init__(self, id, model, amino_acid, RNA):
        ProcessData.__init__(self, id, model)
        model.tRNA_data.append(self)
        self.amino_acid = amino_acid
        self.RNA = RNA
        self.tRNA_keff = 2.39 * mu / (mu + 0.391)
