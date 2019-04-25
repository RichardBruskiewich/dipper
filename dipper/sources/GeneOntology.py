import csv
import re
import logging
import gzip
import io
import sys
import os

import yaml

from dipper.sources.ZFIN import ZFIN
from dipper.sources.WormBase import WormBase
from dipper.sources.Source import Source
from dipper.models.assoc.Association import Assoc
from dipper.models.assoc.G2PAssoc import G2PAssoc
from dipper.models.Genotype import Genotype
from dipper.models.Reference import Reference
from dipper.models.Model import Model
from dipper.utils.GraphUtils import GraphUtils


LOG = logging.getLogger(__name__)
GOGA = 'http://current.geneontology.org/annotations' # get gene annotation from current.geneontology.com, which is the last official release (but not the bleeding edge)
FTPEBI = 'ftp://ftp.uniprot.org/pub/databases/'     # best for North America
UPCRKB = 'uniprot/current_release/knowledgebase/'


class GeneOntology(Source):
    """
    This is the parser for the
    [Gene Ontology Annotations](http://www.geneontology.org),
    from which we process gene-process/function/subcellular
    location associations.

    We generate the GO graph to include the following information:
    * genes
    * gene-process
    * gene-function
    * gene-location

    We process only a subset of the organisms:

    Status: IN PROGRESS / INCOMPLETE

    """

    files = {
        '9615': {
            'file': 'goa_dog.gaf.gz',
            'url': GOGA + '/goa_dog.gaf.gz'},
        '7227': {
            'file': 'fb.gaf.gz',
            'url': GOGA + '/fb.gaf.gz'},
        '7955': {
            'file': 'zfin.gaf.gz',
            'url': GOGA + '/zfin.gaf.gz'},
        '10090': {
            'file': 'mgi.gaf.gz',
            'url': GOGA + '/mgi.gaf.gz'},
        '10116': {
            'file': 'rgd.gaf.gz',
            'url': GOGA + '/rgd.gaf.gz'},
        '6239': {
            'file': 'wb.gaf.gz',
            'url': GOGA + '/wb.gaf.gz'},
        '9823': {
            'file': 'goa_pig.gaf.gz',
            'url': GOGA + '/goa_pig.gaf.gz'},
        '9031': {
            'file': 'goa_chicken.gaf.gz',
            'url': GOGA + '/goa_chicken.gaf.gz'},
        '9606': {
            'file': 'goa_human.gaf.gz',
            'url': GOGA + '/goa_human.gaf.gz'},
        '9913': {
            'file': 'goa_cow.gaf.gz',
            'url': GOGA + '/goa_cow.gaf.gz'},
        '559292': {
            'file': 'sgd.gaf.gz',
            'url': GOGA + '/sgd.gaf.gz'},
        '4896': {
            'file': 'pombase.gaf.gz',
            'url': GOGA + '/pombase.gaf.gz'},
        # consider this after most others - should this be part of GO?
        # 'multispecies': {
        #   'file': 'gene_association.goa_uniprot.gz',
        #   'url': FTPEBI + 'GO/goa/UNIPROT/gene_association.goa_uniprot.gz'},
        'go-references': {
            'file': 'GO.references',
            'url': 'http://www.geneontology.org/doc/GO.references'}, # Quoth the header of this file: "This file is DEPRECATED. Please see go-refs.json relative to this location" (http://current.geneontology.org/metadata/go-refs.json)
        'id-map': {  # 5GB mapping file takes 6 hours to DL ... maps UniProt to Ensembl
            'file': 'idmapping_selected.tab.gz',
            'url':  FTPEBI + UPCRKB + 'idmapping/idmapping_selected.tab.gz'
        }
    }
    # consider moving the go-ref and id-map above to here in map_files
    map_files = {
        'eco_map': 'http://purl.obolibrary.org/obo/eco/gaf-eco-mapping.txt',
    }

    def __init__(self, graph_type, are_bnodes_skolemized, tax_ids=None):
        super().__init__(
            graph_type,
            are_bnodes_skolemized,
            'go',
            ingest_title='Gene Ontology',
            ingest_url='http://www.geneontology.org',
            license_url=None,
            data_rights='http://geneontology.org/page/use-and-license'
            # file_handle=None
        )

        # Defaults
        self.tax_ids = tax_ids
        self.test_ids = list()
        if self.tax_ids is None:
            self.tax_ids = [9606, 10090, 7955]
            LOG.info("No taxa set.  Defaulting to %s", str(tax_ids))
        else:
            LOG.info("Filtering on the following taxa: %s", str(tax_ids))

        if 'gene' not in self.all_test_ids:
            LOG.warning("not configured with gene test ids.")
        else:
            self.test_ids = self.all_test_ids['gene']

        # build the id map for mapping uniprot ids to genes ... ONCE
        self.uniprot_entrez_id_map = self.get_uniprot_entrez_id_map()
        self.eco_map = self.get_eco_map(self.map_files['eco_map'])
        return

    def fetch(self, is_dl_forced=False):
        self.get_files(is_dl_forced)
        return

    def parse(self, limit=None):
        if limit is not None:
            LOG.info("Only parsing first %s rows of each file", limit)
        LOG.info("Parsing files...")

        if self.test_only:
            self.test_mode = True

        for txid_num in self.files:

            if txid_num in ['go-references', 'id-map']:
                continue

            if not self.test_mode and int(txid_num) not in self.tax_ids:
                continue

            gaffile = '/'.join((self.rawdir, self.files.get(txid_num)['file']))
            self.process_gaf(gaffile, limit, self.uniprot_entrez_id_map, self.eco_map)

        LOG.info("Finished parsing.")

        return

    def process_gaf(self, file, limit, id_map=None, eco_map=None):

        if self.test_mode:
            graph = self.testgraph
        else:
            graph = self.graph

        model = Model(graph)
        geno = Genotype(graph)
        LOG.info("Processing Gene Associations from %s", file)
        line_counter = 0
        uniprot_hit = 0
        uniprot_miss = 0
        if 7955 in self.tax_ids:
            zfin = ZFIN(self.graph_type, self.are_bnodes_skized)
        if 6239 in self.tax_ids:
            wbase = WormBase(self.graph_type, self.are_bnodes_skized)

        with gzip.open(file, 'rb') as csvfile:
            filereader = csv.reader(
                io.TextIOWrapper(csvfile, newline=""), delimiter='\t', quotechar='\"')
            for row in filereader:
                line_counter += 1
                # comments start with exclamation
                if re.match(r'!', ''.join(row)):
                    continue

                if len(row) > 17 or len(row) < 15:
                    LOG.warning(
                        "Wrong number of columns %i, expected 15 or 17\n%s",
                        len(row), row)
                    continue

                if 17 > len(row) >= 15:
                    row += [""] * (17 - len(row))

                (dbase,
                 gene_num,
                 gene_symbol,
                 qualifier,
                 go_id,
                 ref,
                 eco_symbol,
                 with_or_from,
                 aspect,
                 gene_name,
                 gene_synonym,
                 object_type,
                 taxon,
                 date,
                 assigned_by,
                 annotation_extension,
                 gene_product_form_id) = row

                # test for required fields
                if (dbase == '' or gene_num == '' or gene_symbol == '' or
                        go_id == '' or ref == '' or eco_symbol == '' or
                        aspect == '' or object_type == '' or taxon == '' or
                        date == '' or assigned_by == ''):
                    LOG.error(
                        "Missing required part of annotation on row %d:\n"+'\t'
                        .join(row), line_counter)
                    continue

                # deal with qualifier NOT, contributes_to, colocalizes_with
                if re.search(r'NOT', qualifier):
                    continue

                if dbase in self.localtt:
                    dbase = self.localtt[dbase]
                uniprotid = None
                gene_id = None
                if dbase == 'UniProtKB':
                    if id_map is not None and gene_num in id_map:
                        gene_id = id_map[gene_num]
                        uniprotid = ':'.join((dbase, gene_num))
                        (dbase, gene_num) = gene_id.split(':')
                        uniprot_hit += 1
                    else:
                        # LOG.warning(
                        #   "UniProt id %s  is without a 1:1 mapping to entrez/ensembl",
                        #    gene_num)
                        uniprot_miss += 1
                        continue
                else:
                    gene_num = gene_num.split(':')[-1]  # last
                    gene_id = ':'.join((dbase, gene_num))

                if self.test_mode and not(
                        re.match(r'NCBIGene', gene_id) and
                        int(gene_num) in self.test_ids):
                    continue

                model.addClassToGraph(gene_id, gene_symbol)
                if gene_name != '':
                    model.addDescription(gene_id, gene_name)
                if gene_synonym != '':
                    for syn in re.split(r'\|', gene_synonym):
                        model.addSynonym(gene_id, syn.strip())
                if re.search(r'\|', taxon):
                    # TODO add annotations with >1 taxon
                    LOG.info(
                        ">1 taxon (%s) on line %d.  skipping", taxon, line_counter)
                else:
                    tax_id = re.sub(r'taxon:', 'NCBITaxon:', taxon)
                    geno.addTaxon(tax_id, gene_id)

                assoc = Assoc(graph, self.name)
                assoc.set_subject(gene_id)
                assoc.set_object(go_id)

                try:
                    eco_id = eco_map[eco_symbol]
                    assoc.add_evidence(eco_id)
                except KeyError:
                    LOG.error("Evidence code (%s) not mapped", eco_symbol)

                refs = re.split(r'\|', ref)
                for ref in refs:
                    ref = ref.strip()
                    if ref != '':
                        prefix = ref.split(':')[0]  # sidestep 'MGI:MGI:'
                        if prefix in self.localtt:
                            prefix = self.localtt[prefix]
                        ref = ':'.join((prefix, ref.split(':')[-1]))
                        refg = Reference(graph, ref)
                        if prefix == 'PMID':
                            ref_type = self.globaltt['journal article']
                            refg.setType(ref_type)
                        refg.addRefToGraph()
                        assoc.add_source(ref)

                # TODO add the source of the annotations from assigned by?

                rel = self.resolve(aspect, mandatory=False)
                if rel is not None and aspect == rel:
                    if aspect == 'F' and re.search(r'contributes_to', qualifier):
                        assoc.set_relationship(self.globaltt['contributes to'])
                    else:
                        LOG.error(
                            "Aspect: %s with qualifier: %s  is not recognized",
                            aspect, qualifier)
                elif rel is not None:
                    assoc.set_relationship(rel)
                    assoc.add_association_to_graph()
                else:
                    LOG.warning("No predicate for association \n%s\n", str(assoc))

                if uniprotid is not None:
                    assoc.set_description('Mapped from ' + uniprotid)
                # object_type should be one of:
                # protein_complex; protein; transcript; ncRNA; rRNA; tRNA;
                # snRNA; snoRNA; any subtype of ncRNA in the Sequence Ontology.
                # If the precise product type is unknown,
                # gene_product should be used
                #######################################################################

                # Derive G2P Associations from IMP annotations
                # in version 2.1 Pipe will indicate 'OR'
                # and Comma will indicate 'AND'.
                # in version 2.0, multiple values are separated by pipes
                # where the pipe has been used to mean 'AND'
                if eco_symbol == 'IMP' and with_or_from != '':
                    withitems = re.split(r'\|', with_or_from)
                    phenotypeid = go_id+'PHENOTYPE'
                    # create phenotype associations
                    for i in withitems:
                        if i == '' or re.match(
                                r'(UniProtKB|WBPhenotype|InterPro|HGNC)', i):
                            LOG.warning(
                                "Don't know what having a uniprot id " +
                                "in the 'with' column means of %s", uniprotid)
                            continue
                        i = re.sub(r'MGI\:MGI\:', 'MGI:', i)
                        i = re.sub(r'WB:', 'WormBase:', i)

                        # for worms and fish, they might give a RNAi or MORPH
                        # in these cases make a reagent-targeted gene
                        if re.search('MRPHLNO|CRISPR|TALEN', i):
                            targeted_gene_id = zfin.make_targeted_gene_id(gene_id, i)
                            geno.addReagentTargetedGene(i, gene_id, targeted_gene_id)
                            # TODO PYLINT why is this needed?
                            # Redefinition of assoc type from
                            # dipper.models.assoc.Association.Assoc to
                            # dipper.models.assoc.G2PAssoc.G2PAssoc
                            assoc = G2PAssoc(
                                graph, self.name, targeted_gene_id, phenotypeid)
                        elif re.search(r'WBRNAi', i):
                            targeted_gene_id = wbase.make_reagent_targeted_gene_id(
                                gene_id, i)
                            geno.addReagentTargetedGene(i, gene_id, targeted_gene_id)
                            assoc = G2PAssoc(
                                graph, self.name, targeted_gene_id, phenotypeid)
                        else:
                            assoc = G2PAssoc(graph, self.name, i, phenotypeid)
                        for ref in refs:
                            ref = ref.strip()
                            if ref != '':
                                prefix = ref.split(':')[0]
                                if prefix in self.localtt:
                                    prefix = self.localtt[prefix]
                                ref = ':'.join((prefix, ref.split(':')[-1]))
                                assoc.add_source(ref)
                                # experimental phenotypic evidence
                                assoc.add_evidence(
                                    self.globaltt['experimental phenotypic evidence'])
                        assoc.add_association_to_graph()
                        # TODO should the G2PAssoc be
                        # the evidence for the GO assoc?

                if not self.test_mode and limit is not None and line_counter > limit:
                    break
            uniprot_tot = (uniprot_hit + uniprot_miss)
            uniprot_per = 0.0
            if uniprot_tot != 0:
                uniprot_per = 100.0 * uniprot_hit / uniprot_tot
            LOG.info(
                "Uniprot: %f.2%% of %i benifited from the 1/4 day id mapping download",
                uniprot_per, uniprot_tot)
        return

    def get_uniprot_entrez_id_map(self):
        taxon_digest = GraphUtils.digest_id(str(self.tax_ids))
        id_map = {}
        smallfile = '/'.join((self.rawdir, 'id_map_' + taxon_digest + '.yaml'))
        bigfile = '/'.join((self.rawdir, self.files['id-map']['file']))

        # if processed smallfile exists and is newer use it instesd
        if os.path.isfile(smallfile) and \
                os.path.getctime(smallfile) > os.path.getctime(bigfile):
            LOG.info("Using the cheap mapping file %s", smallfile)
            with open(smallfile, 'r') as fh:
                id_map = yaml.safe_load(fh)
        else:
            LOG.info(
                "Expensive Mapping from Uniprot ids to Entrez/ENSEMBL gene ids for %s",
                str(self.tax_ids))
            self.fetch_from_url(self.files['id-map']['url'], bigfile)
            with gzip.open(bigfile, 'rb') as csvfile:
                csv.field_size_limit(sys.maxsize)
                filereader = csv.reader(  # warning this file is over 10GB unzipped
                    io.TextIOWrapper(
                        csvfile, newline=""), delimiter='\t', quotechar='\"')
                for row in filereader:
                    (uniprotkb_ac, uniprotkb_id, geneid, refseq, gi, pdb, go,
                     uniref100, unifref90, uniref50, uniparc, pir, ncbitaxon, mim,
                     unigene, pubmed, embl, embl_cds, ensembl, ensembl_trs,
                     ensembl_pro, other_pubmed) = row
                    if int(ncbitaxon) not in self.tax_ids:
                        continue
                    genid = geneid.strip()
                    if geneid != '' and ';' not in genid:
                        id_map[uniprotkb_ac.strip()] = 'NCBIGene:' + genid
                    elif ensembl.strip() != '' and ';' not in ensembl:
                        id_map[uniprotkb_ac.strip()] = 'ENSEMBL:' + ensembl.strip()

            LOG.info("Writing id_map out as %s", smallfile)
            with open(smallfile, 'w') as fh:
                yaml.dump(id_map, fh)

        LOG.info(
            "Acquired %i 1:1 uniprot to [entrez|ensembl] mappings", len(id_map.keys()))

        return id_map

    def getTestSuite(self):
        import unittest
        from tests.test_geneontology import GeneOntologyTestCase

        test_suite = unittest.TestLoader().loadTestsFromTestCase(GeneOntologyTestCase)

        return test_suite
