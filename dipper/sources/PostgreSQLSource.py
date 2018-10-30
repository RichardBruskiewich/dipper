
import logging
import os
import psycopg2
from dipper.sources.Source import Source

LOG = logging.getLogger(__name__)


class PostgreSQLSource(Source):
    """
    Class for interfacing with remote Postgres databases
    """

    files = {}

    def __init__(
            self,
            graph_type,
            are_bnodes_skolemized,
            name=None,
            ingest_title=None,
            ingest_url=None,
            license_url=None,
            data_rights=None,
            file_handle=None
    ):

        super().__init__(
            graph_type,
            are_bnodes_skolemized,
            name,
            ingest_title,
            ingest_url,
            license_url,
            data_rights,
            file_handle)

        # used downstream but handled in Source
        # globaltt = self.globaltt
        # globaltcid = self.globaltcid
        # all_test_ids = self.all_test_ids
        return

    def fetch_from_pgdb(self, tables, cxn, limit=None, force=False):
        """
        Will fetch all Postgres tables from the specified database
            in the cxn connection parameters.
        This will save them to a local file named the same as the table,
            in tab-delimited format, including a header.
        :param tables: Names of tables to fetch
        :param cxn: database connection details
        :param limit: A max row count to fetch for each table
        :return: None
        """

        con = None
        try:
            con = psycopg2.connect(
                host=cxn['host'], database=cxn['database'], port=cxn['port'],
                user=cxn['user'], password=cxn['password'])
            cur = con.cursor()
            for tab in tables:
                LOG.info("Fetching data from table %s", tab)
                self._getcols(cur, tab)
                query = ' '.join(("SELECT * FROM", tab))
                countquery = ' '.join(("SELECT COUNT(*) FROM", tab))
                if limit is not None:
                    query = ' '.join((query, "LIMIT", str(limit)))
                    countquery = ' '.join((countquery, "LIMIT", str(limit)))

                outfile = '/'.join((self.rawdir, tab))

                filerowcount = -1
                tablerowcount = -1
                if not force:
                    # check local copy.  assume that if the # rows are the same,
                    # that the table is the same
                    # TODO may want to fix this assumption
                    if os.path.exists(outfile):
                        # get rows in the file
                        filerowcount = self.file_len(outfile)
                        LOG.info(
                            "(%s) rows in local file for table %s", filerowcount, tab)

                    # get rows in the table
                    # tablerowcount=cur.rowcount
                    cur.execute(countquery)
                    tablerowcount = cur.fetchone()[0]

                # rowcount-1 because there's a header
                if force or filerowcount < 0 or (filerowcount-1) != tablerowcount:
                    if force:
                        LOG.info("Forcing download of %s", tab)
                    else:
                        LOG.info(
                            "%s local (%d) different from remote (%d); fetching.",
                            tab, filerowcount, tablerowcount)
                    # download the file
                    LOG.info("COMMAND:%s", query)
                    outputquery = """
    COPY ({0}) TO STDOUT WITH DELIMITER AS '\t' CSV HEADER""".format(query)
                    with open(outfile, 'w') as f:
                        cur.copy_expert(outputquery, f)
                else:
                    LOG.info("local data same as remote; reusing.")

        finally:
            if con:
                con.close()
        return

    def fetch_query_from_pgdb(self, qname, query, con, cxn, limit=None, force=False):
        """
        Supply either an already established connection, or connection parameters.
        The supplied connection will override any separate cxn parameter
        :param qname:  The name of the query to save the output to
        :param query:  The SQL query itself
        :param con:  The already-established connection
        :param cxn: The postgres connection information
        :param limit: If you only want a subset of rows from the query
        :return:
        """
        if con is None and cxn is None:
            LOG.error("ERROR: you need to supply connection information")
            return
        if con is None and cxn is not None:
            con = psycopg2.connect(
                host=cxn['host'], database=cxn['database'], port=cxn['port'],
                user=cxn['user'], password=cxn['password'])

        outfile = '/'.join((self.rawdir, qname))
        cur = con.cursor()
        # wrap the query to get the count
        countquery = ' '.join(("SELECT COUNT(*) FROM (", query, ") x"))
        if limit is not None:
            countquery = ' '.join((countquery, "LIMIT", str(limit)))

        # check local copy.
        # assume that if the # rows are the same, that the table is the same
        # TEC - opinion:
        #    the only thing to assume is that if the counts are different
        #    is the data could not be the same.
        #
        #    i.e: for MGI, the dbinfo table has a single row that changes
        #    to check if they are the same sort & compare digests. (
        filerowcount = -1
        tablerowcount = -1
        if not force:
            if os.path.exists(outfile):
                # get rows in the file
                filerowcount = self.file_len(outfile)
                LOG.info("INFO: rows in local file: %s", filerowcount)

            # get rows in the table
            # tablerowcount=cur.rowcount
            cur.execute(countquery)
            tablerowcount = cur.fetchone()[0]

        # rowcount-1 because there's a header
        if force or filerowcount < 0 or (filerowcount-1) != tablerowcount:
            if force:
                LOG.info("Forcing download of %s", qname)
            else:
                LOG.info(
                    "%s local (%s) different from remote (%s); fetching.",
                    qname, filerowcount, tablerowcount)
            # download the file
            LOG.debug("COMMAND:%s", query)
            outputquery = """
    COPY ({0}) TO STDOUT WITH DELIMITER AS '\t' CSV HEADER""".format(query)
            with open(outfile, 'w') as f:
                cur.copy_expert(outputquery, f)
            # Regenerate row count to check integrity
            filerowcount = self.file_len(outfile)
            if (filerowcount-1) < tablerowcount:
                raise Exception(
                    "Download from %s failed, %s != %s", cxn['host'] + ':' +
                    cxn['database'], (filerowcount-1), tablerowcount)
            elif (filerowcount-1) > tablerowcount:
                LOG.warning(
                    "Fetched from %s more rows in file (%s) than reported in count(%s)",
                    cxn['host'] + ':'+cxn['database'], (filerowcount-1), tablerowcount)
        else:
            LOG.info("local data same as remote; reusing.")

        return

    # TODO generalize this to a set of utils
    @staticmethod
    def _getcols(cur, table):
        """
        Will execute a pg query to get the column names for the given table.
        :param cur:
        :param table:
        :return:
        """
        query = ' '.join(("SELECT * FROM", table, "LIMIT 0"))  # for testing

        cur.execute(query)
        colnames = [desc[0] for desc in cur.description]
        LOG.info("COLS (%s): %s", table, colnames)

        return

    # abstract
    def fetch(self, is_dl_forced=False):
        """
        abstract method to fetch all data from an external resource.
        this should be overridden by subclasses
        :return: None

        """
        raise NotImplementedError

    def parse(self, limit):
        """
        abstract method to parse all data from an external resource,
        that was fetched in fetch() this should be overridden by subclasses
        :return: None

        """
        raise NotImplementedErrors

