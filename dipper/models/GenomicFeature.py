__author__ = 'nicole'

import re

from rdflib import URIRef,Literal
from rdflib.namespace import RDF,XSD

from dipper import curie_map
from dipper.utils.GraphUtils import GraphUtils
from dipper.utils.CurieUtil import CurieUtil
from dipper.models.Assoc import Assoc


class Feature() :
    '''
    Dealing with genomic features here.  By default they are all faldo:Regions.
    We use SO for typing genomic features.
    At the moment, RO:has_subsequence is the default relationship between the regions, but this should be tested/verified.

    TODO: the graph additions are in the addXToFeature functions, but should be separated.
    TODO: this will need to be extended to properly deal with fuzzy positions in faldo.
    '''

    object_properties = {
        'location' : 'faldo:location',
        'begin' : 'faldo:begin',
        'end' : 'faldo:end',
        'reference' : 'faldo:reference',
        'gene_product_of' : 'RO:0002204',
        'has_gene_product' : 'RO:0002205',
        'is_about' : 'IAO:00000136',
        'has_subsequence' : 'RO:0002524',
        'is_subsequence_of' : 'RO:0002525',
    }

    data_properties = {
        'position' : 'faldo:position',
    }

    annotation_properties = {    }

    properties = object_properties.copy()
    properties.update(data_properties)
    properties.update(annotation_properties)

    types = {
        'region' : 'faldo:Region',
        'Position' : 'faldo:Position',  #big P for Position type.  little p for position property
        'chromosome' : 'SO:0000340',
        'chromosome_arm' : 'SO:0000105',
        'chromosome_band' : 'SO:0000341',
        'chromosome_part' : 'SO:0000830',
        'plus_strand' : 'faldo:PlusStrandPosition',
        'minus_strand' : 'faldo:MinusStrandPosition',
        'both_strand' : 'faldo:BothStrandPosition',
        'score' : 'SO:0001685',  #FIXME - this is not a good solution, too generic
        'reference_genome' : 'SO:0001505'
    }

    def __init__(self,id,label,type,description=None):
        self.id = id
        self.label = label
        self.type = type
        self.description = description
        self.gu = GraphUtils(curie_map.get())
        self.start = None
        self.stop = None
        return


    def addFeatureStartLocation(self,coordinate,reference_id,strand=None,position_types=None):
        """
        Adds coordinate details for the start of this feature.
        :param coordinate:
        :param reference_id:
        :param strand:
        :param position_types:
        :return:
        """
        #make an object for the start, which has:
        #{coordinate : integer, reference : reference_id, types = []}
        self.start = self._getLocation(coordinate,reference_id,strand,position_types)

        return

    def addFeatureEndLocation(self,coordinate,reference_id,strand=None,position_types=None):
        """
        Adds the coordinate details for the end of this feature
        :param coordinate:
        :param reference_id:
        :param strand:
        :return:
        """
        self.stop = self._getLocation(coordinate,reference_id,strand,position_types)

        return

    def _getLocation(self,coordinate,reference_id,strand,position_types):
        """
        Make an object for the location, which has:
        {coordinate : integer, reference : reference_id, types = []}
        where the strand is indicated in the type array
        :param coordinate:
        :param reference_id:
        :param strand:
        :param position_types:
        :return:
        """
        loc = {}
        loc['coordinate'] = coordinate
        loc['reference'] = reference_id
        loc['type'] = []
        strand_id = self._getStrandType(strand)
        if (strand_id is not None):
            loc['type'].append(strand_id)
        if position_types is None:
            loc['type'].append(self.types['Position'])
        else:
            loc['type'] += position_types

        return loc

    def _getStrandType(self,strand):
        """

        :param strand:
        :return:
        """
        #TODO make this a dictionary/enum:  PLUS, MINUS, BOTH
        strand_id = None
        if (strand == '+'):
            self.strand_id = self.types['plus_strand']
        elif (strand == '-'):
            self.strand_id = self.types['minus_strand']
        elif (strand == '.' or strand is None):
            self.strand_id = self.types['both_strand']
        else:
            print("WARN: strand type could not be mapped:",strand)

        return strand_id


    def addFeatureToGraph(self,graph):
        '''
        We make the assumption here that all features are instances.
        The features are located on a region, which begins and ends with faldo:Position
        The feature locations leverage the Faldo model, which has a general structure like:
        Triples:
        feature_id a feature_type (individual)
            faldo:location region_id
        region_id a faldo:region
            faldo:begin start_position
            faldo:end end_position
        start_position a (any of: faldo:(((Both|Plus|Minus)Strand)|Exact)Position)
            faldo:position Integer(numeric position)
            faldo:reference reference_id
        end_position a (any of: faldo:(((Both|Plus|Minus)Strand)|Exact)Position)
            faldo:position Integer(numeric position)
            faldo:reference reference_id

        :param graph:
        :return:
        '''
        self.gu.addIndividualToGraph(graph,self.id,self.label,self.type,self.description)

        #create a region that has the begin/end positions
        region_id = ':_'+self.id+'Region'  #FIXME make this anonymous
        self.gu.addTriple(graph,self.id,self.properties['location'],region_id)

        self.gu.addIndividualToGraph(graph,region_id,None,'faldo:Region')
        #add the start/end positions to the region
        if (self.start is not None):
            self.gu.addTriple(graph,region_id,self.properties['begin'],self._makePositionId(self.start['reference'],self.start['coordinate']))
        if (self.stop is not None):
            self.gu.addTriple(graph,region_id,self.properties['end'],self._makePositionId(self.start['reference'],self.stop['coordinate']))

        #{coordinate : integer, reference : reference_id, types = []}

        if self.start is not None:
            self.addPositionToGraph(graph,self.start['reference'],self.start['coordinate'],self.start['type'])
        if self.stop is not None:
            self.addPositionToGraph(graph,self.stop['reference'],self.stop['coordinate'],self.stop['type'])


        return

    def _makePositionId(self,reference,coordinate,types=None):
        i = ':_'
        if reference is not None:
            i += reference +'-'
        i += str(coordinate)      #just in case it isn't a string already
        if (types is not None):
            t = types.sort
            i += ('-').join(t)
        return i

    def addPositionToGraph(self,graph,reference_id,position,position_types=None,strand=None):
        """
        Add the positional information to the graph, following the faldo model.
        We assume that if the strand is None, it is meaning "Both".
        Triples:
        my_position a (any of: faldo:(((Both|Plus|Minus)Strand)|Exact)Position)
            faldo:position Integer(numeric position)
            faldo:reference reference_id

        :param graph:
        :param reference_id:
        :param position:
        :param position_types:
        :param strand:
        :return:
        """

        iid = self._makePositionId(reference_id,position)
        n = self.gu.getNode(iid)
        pos = self.gu.getNode(self.properties['position'])
        ref = self.gu.getNode(self.properties['reference'])
        graph.add((n,pos,Literal(position,datatype=XSD['integer'])))
        graph.add((n,ref,self.gu.getNode(reference_id)))
        if position_types is not None:
            for t in position_types:
                graph.add((n,RDF['type'],self.gu.getNode(t)))
        if strand is not None:
            s=strand
            if not re.match('faldo',strand):
                #not already mapped to faldo, so expect we need to map it
                s = self._getStrandType(strand)
        else:
            s = self.types['both_strand']
        graph.add((n,RDF['type'],self.gu.getNode(s)))

        return iid


    def addSubsequenceOfFeature(self,graph,parentid):
        '''
        This will add a triple like:
        feature subsequence_of parent
        :param graph:
        :param parentid:
        :return:
        '''
        n = self.gu.getNode(self.id)
        p = self.gu.getNode(parentid)
        subsequence=self.gu.getNode(self.properties['is_subsequence_of'])
        graph.add((n,subsequence,p))
        return


    def addTaxonToFeature(self,graph,taxonid):
        '''
        Given the taxon id, this will add the following triple:
        feature in_taxon taxonid
        :param graph:
        :param id:
        :param taxonid:
        :return:
        '''
        self.taxon = taxonid
        n = self.gu.getNode(self.id)
        t = self.gu.getNode(self.taxon)
        intaxon=self.gu.getNode(Assoc.properties['in_taxon'])
        graph.add((n,intaxon,t))
        return

    def loadAllProperties(self,graph):

        prop_dict = {
            Assoc().ANNOTPROP : self.annotation_properties,
            Assoc().OBJECTPROP : self.object_properties,
            Assoc().DATAPROP : self.data_properties
        }

        for p in prop_dict:
            self.gu.loadProperties(graph,prop_dict.get(p),p)

        return

def makeChromID(chrom, taxon=None):
    '''
    This will take a chromosome number and a NCBI taxon number,
    and create a unique identifier for the chromosome.  These identifiers
    are made in the @base space like:
    Homo sapiens (9606) chr1 ==> :9606chr1
    Mus musculus (10090) chrX ==> :10090chrX

    :param chrom: the chromosome (preferably without any chr prefix)
    :param taxon: the numeric portion of the taxon id
    :return:
    '''
    if (taxon is None):
        print('WARN: no taxon for this chrom.  you may have conflicting ids')
        taxon = ''
    # replace any chr-like prefixes with blank to standardize
    c = re.sub('ch(r?)[omse]*', '', chrom)
    id = ('').join((':', taxon, 'chr', c))
    return id
