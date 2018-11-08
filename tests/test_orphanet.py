#!/usr/bin/env python3

import unittest
import logging
import os
# from tests.test_source import SourceTestCase
from dipper.sources.Orphanet import Orphanet
from dipper.utils.TestUtils import TestUtils
from dipper.graph.RDFGraph import RDFGraph


logging.getLogger().setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class GeneVariantDiseaseTest(unittest.TestCase):

    def setUp(self):
        """
        """
        self.test_util = TestUtils()
        self.orphanet = Orphanet('rdf_graph', True)
        # Override so tests don't break when we update terms
        self.globaltt = self.orphanet.open_and_parse_yaml(
            os.path.join(os.path.dirname(__file__), './resources/test_terms.yaml'))
        self.orphanet.rawdir = os.path.join(
            os.path.dirname(__file__), 'resources/orphanet')

    def tearDown(self):
        self.orphanet = None
        return

    def test_germline_variant_to_disease(self):
        self.orphanet.graph = RDFGraph()  # Reset graph
        self.orphanet.files['disease-gene']['file'] = 'orph-germline.xml'

        self.orphanet._process_diseasegene(limit=None)
        logger.debug(
            "Reference graph: %s",
            self.orphanet.graph.serialize(format="turtle").decode("utf-8")
        )
        expected_triples = """
MONARCH:b2cd4dfacc21d0e28c39 a OBAN:association ;
    RO:0002558 ECO:0000322 ;
    OBAN:association_has_object ORPHA:938475 ;
    OBAN:association_has_predicate RO:0003303 ;
    OBAN:association_has_subject <https://monarchinitiative.org/.well-known/genid/b56f798350412a34> .

ENSEMBL:ENSG00000166813 a owl:Class .

HGNC:30497 a owl:Class .

ORPHA:268061 a owl:Class ;
    rdfs:label "KS1" ;
    dc:description "kinesin family member 7" ;
    oboInOwl:hasExactSynonym "KAS1" ;
    rdfs:subClassOf OBO:SO_0001217 ;
    owl:equivalentClass ENSEMBL:ENSG00000166813,
        HGNC:30497 .

<https://monarchinitiative.org/.well-known/genid/b56f798350412a34> a GENO:0000002 ;
    rdfs:label "germline variant of KS1" ;
    GENO:0000418 ORPHA:268061 ;
    RO:0003303 ORPHA:938475 ;
    :MONARCH_anonymous true ;
    :has_cell_origin GENO:0000900 .

ORPHA:938475 a owl:Class ;
    rdfs:label "too much unit testing disorder" .
        """
        self.assertTrue(self.test_util.test_graph_equality(
            expected_triples, self.orphanet.graph))

    def test_germline_lof_variant_to_disease(self):
        self.orphanet.graph = RDFGraph()  # Reset graph
        self.orphanet.files['disease-gene']['file'] = 'orph-germline-lof.xml'

        self.orphanet._process_diseasegene(limit=None)
        logger.debug(
            "Reference graph: %s",
            self.orphanet.graph.serialize(format="turtle").decode("utf-8")
        )
        expected_triples = """
MONARCH:b53dada0eb229a75e705 OBAN:association ;
    RO:0002558 ECO:0000322 ;
    OBAN:association_has_object ORPHA:938475 ;
    OBAN:association_has_predicate RO:0003303 ;
    OBAN:association_has_subject <https://monarchinitiative.org/.well-known/genid/ba0884fb61004110> .

ORPHA:268061 a owl:Class ;
    rdfs:label "KS1" ;
    dc:description "kinesin family member 7" ;
    oboInOwl:hasExactSynonym "KAS1" ;
    rdfs:subClassOf SO:0001217 .

<https://monarchinitiative.org/.well-known/genid/ba0884fb61004110> a GENO:0000002 ;
    rdfs:label "germline loss of function variant of KS1" ;
    GENO:0000418 ORPHA:268061 ;
    RO:0003303 ORPHA:938475 ;
    :MONARCH_anonymous true ;
    :has_cell_origin GENO:0000900 ;
    :has_functional_consequence SO:0002054 .

ORPHA:938475 a owl:Class ;
    rdfs:label "too much unit testing disorder" .
        """
        self.assertTrue(self.test_util.test_graph_equality(
            expected_triples, self.orphanet.graph))

    def test_gene_to_disease(self):
        self.orphanet.graph = RDFGraph()  # Reset graph
        self.orphanet.files['disease-gene']['file'] = 'orph-no-variant.xml'

        self.orphanet._process_diseasegene(limit=None)
        logger.debug(
            "Reference graph: %s",
            self.orphanet.graph.serialize(format="turtle") .decode("utf-8")
        )
        expected_triples = """
MONARCH:b64684a0ea6ae59fdb09 a OBAN:association ;
    RO:0002558 ECO:0000322 ;
    OBAN:association_has_object ORPHA:938475 ;
    OBAN:association_has_predicate RO:0003304 ;
    OBAN:association_has_subject ORPHA:268061 .

ORPHA:268061 a owl:Class ;
    rdfs:label "KS1" ;
    RO:0003304 ORPHA:938475 ;
    dc:description "kinesin family member 7" ;
    oboInOwl:hasExactSynonym "KAS1" ;
    rdfs:subClassOf SO:0001217 .

ORPHA:938475 a owl:Class ;
    rdfs:label "too much unit testing disorder" .
        """
        self.assertTrue(self.test_util.test_graph_equality(
            expected_triples, self.orphanet.graph))

    def test_unmapped_disease_assoc_type(self):
        """
        Test that a gene disease type that we have
        not mapped in translationtable/orphanet.yaml
        raises a ValueError
        """
        self.orphanet.graph = RDFGraph()  # Reset graph
        self.orphanet.files['disease-gene']['file'] = 'orph-no-mapping.xml'
        self.assertRaises(
            ValueError, lambda: self.orphanet._process_diseasegene(limit=None))


if __name__ == '__main__':
    unittest.main()
