import logging
import csv
import re

from dipper.sources.Source import Source
from dipper.models.Genotype import Genotype
from dipper.models.Model import Model
from dipper.models.GenomicFeature import Feature, makeChromID
from dipper.utils.DipperUtil import DipperUtil


LOG = logging.getLogger(__name__)


class HGNC(Source):
    """
    This is the processing module for HGNC.

    We create equivalences between HGNC identifiers and ENSEMBL and NCBIGene.
    We also add the links to cytogenic locations for the gene features.

    """

    EBIFTP = 'ftp://ftp.ebi.ac.uk/pub/databases/genenames/'
    files = {
        'genes': {
            'file': 'hgnc_complete_set.txt',
            'url': EBIFTP + 'new/tsv/hgnc_complete_set.txt'},
    }

    def __init__(self, graph_type, are_bnodes_skolemized,
                 tax_ids=None, gene_ids=None):
        super().__init__(
            graph_type,
            are_bnodes_skolemized,
            'hgnc',
            ingest_title='HGNC',
            ingest_url='https://www.genenames.org/',
            license_url=None,
            data_rights='ftp://ftp.ebi.ac.uk/pub/databases/genenames/README.txt',
            # file_handle=None
        )

        self.tax_ids = tax_ids
        self.gene_ids = gene_ids

        self.gene_ids = []
        if 'gene' not in self.all_test_ids:
            LOG.warning("not configured with gene test ids.")
        else:
            self.gene_ids = self.all_test_ids['gene']

        self.hs_txid = self.globaltt['Homo sapiens']

        return

    def fetch(self, is_dl_forced=False):

        self.get_files(is_dl_forced)

        return

    def parse(self, limit=None):
        if limit is not None:
            LOG.info("Only parsing first %d rows", limit)

        if self.testOnly:
            self.test_mode = True

        LOG.info("Parsing files...")

        self._process_genes(limit)

        LOG.info("Done parsing files.")

        return

    def _process_genes(self, limit=None):

        if self.test_mode:
            graph = self.testgraph
        else:
            graph = self.graph

        geno = Genotype(graph)
        model = Model(graph)
        raw = '/'.join((self.rawdir, self.files['genes']['file']))
        line_counter = 0
        LOG.info("Processing HGNC genes")

        with open(raw, 'r', encoding="utf8") as csvfile:
            filereader = csv.reader(csvfile, delimiter='\t', quotechar='\"')
            # curl -s ftp://ftp.ebi.ac.uk/pub/databases/genenames/new/tsv/hgnc_complete_set.txt | head -1 | tr '\t' '\n' | grep -n  .
            for row in filereader:
                (hgnc_id,
                 symbol,
                 name,
                 locus_group,
                 locus_type,
                 status,
                 location,
                 location_sortable,
                 alias_symbol,
                 alias_name,
                 prev_symbol,
                 prev_name,
                 gene_family,
                 gene_family_id,
                 date_approved_reserved,
                 date_symbol_changed,
                 date_name_changed,
                 date_modified,
                 entrez_id,
                 ensembl_gene_id,
                 vega_id,
                 ucsc_id,
                 ena,
                 refseq_accession,
                 ccds_id,
                 uniprot_ids,
                 pubmed_id,
                 mgd_id,
                 rgd_id,
                 lsdb,
                 cosmic,
                 omim_id,
                 mirbase,
                 homeodb,
                 snornabase,
                 bioparadigms_slc,
                 orphanet,
                 pseudogene_org,
                 horde_id,
                 merops,
                 imgt,
                 iuphar,
                 kznf_gene_catalog,
                 mamit_trnadb,
                 cd,
                 lncrnadb,
                 enzyme_id,
                 intermediate_filament_db,
                 rna_central_ids) = row

                line_counter += 1

                # skip header
                if line_counter <= 1:
                    continue

                if self.test_mode and entrez_id != '' and \
                        int(entrez_id) not in self.gene_ids:
                    continue

                if name == '':
                    name = None

                if locus_type == 'withdrawn':
                    model.addDeprecatedClass(hgnc_id)
                else:
                    gene_type_id = self.resolve(locus_type, False)  # withdrawn -> None?
                    if gene_type_id != locus_type:
                        model.addClassToGraph(hgnc_id, symbol, gene_type_id, name)
                    model.makeLeader(hgnc_id)

                if entrez_id != '':
                    model.addEquivalentClass(
                        hgnc_id, 'NCBIGene:' + entrez_id)
                if ensembl_gene_id != '':
                    model.addEquivalentClass(
                        hgnc_id, 'ENSEMBL:' + ensembl_gene_id)
                if omim_id != '' and "|" not in omim_id:
                    omim_curie = 'OMIM:' + omim_id
                    if not DipperUtil.is_omim_disease(omim_curie):
                        model.addEquivalentClass(hgnc_id, omim_curie)

                geno.addTaxon(self.hs_txid, hgnc_id)

                # add pubs as "is about"
                if pubmed_id != '':
                    for p in re.split(r'\|', pubmed_id.strip()):
                        if str(p) != '':
                            graph.addTriple(
                                'PMID:' + str(p.strip()),
                                self.globaltt['is_about'], hgnc_id)

                # add chr location
                # sometimes two are listed, like: 10p11.2 or 17q25
                # -- there are only 2 of these FRA10A and MPFD
                # sometimes listed like "1 not on reference assembly"
                # sometimes listed like 10q24.1-q24.3
                # sometimes like 11q11 alternate reference locus
                band = chrom = None
                chr_pattern = r'(\d+|X|Y|Z|W|MT)[pq$]'
                chr_match = re.match(chr_pattern, location)
                if chr_match is not None and len(chr_match.groups()) > 0:
                    chrom = chr_match.group(1)
                    chrom_id = makeChromID(chrom, self.hs_txid, 'CHR')
                    band_pattern = r'([pq][A-H\d]?\d?(?:\.\d+)?)'
                    band_match = re.search(band_pattern, location)
                    feat = Feature(graph, hgnc_id, None, None)
                    if band_match is not None and len(band_match.groups()) > 0:
                        band = band_match.group(1)
                        band = chrom + band
                        # add the chr band as the parent to this gene
                        # as a feature but assume that the band is created
                        # as a class with properties elsewhere in Monochrom
                        band_id = makeChromID(band, self.hs_txid, 'CHR')
                        model.addClassToGraph(band_id, None)
                        feat.addSubsequenceOfFeature(band_id)
                    else:
                        model.addClassToGraph(chrom_id, None)
                        feat.addSubsequenceOfFeature(chrom_id)

                if not self.test_mode and limit is not None and line_counter > limit:
                    break

            # end loop through file

        return

    def get_symbol_id_map(self):
        """
        A convenience method to create a mapping between the HGNC
        symbols and their identifiers.
        :return:

        """

        symbol_id_map = {}
        f = '/'.join((self.rawdir, self.files['genes']['file']))
        with open(f, 'r', encoding="utf8") as csvfile:
            filereader = csv.reader(csvfile, delimiter='\t', quotechar='\"')
            for row in filereader:
                (hgnc_id, symbol, name, locus_group, locus_type, status,
                 location, location_sortable, alias_symbol, alias_name,
                 prev_symbol, prev_name, gene_family, gene_family_id,
                 date_approved_reserved, date_symbol_changed,
                 date_name_changed, date_modified, entrez_id, ensembl_gene_id,
                 vega_id, ucsc_id, ena, refseq_accession, ccds_id, uniprot_ids,
                 pubmed_id, mgd_id, rgd_id, lsdb, cosmic, omim_id, mirbase,
                 homeodb, snornabase, bioparadigms_slc, orphanet,
                 pseudogene_org, horde_id, merops, imgt, iuphar,
                 kznf_gene_catalog, mamit_trnadb, cd, lncrnadb, enzyme_id,
                 intermediate_filament_db) = row

                symbol_id_map[symbol.strip()] = hgnc_id

        return symbol_id_map

    def getTestSuite(self):
        import unittest
        from tests.test_hgnc import HGNCTestCase

        test_suite = unittest.TestLoader().loadTestsFromTestCase(HGNCTestCase)

        return test_suite
