UPSERT_PAPER = """
MERGE (p:Paper {arxiv_id: $arxiv_id})
SET p.title = $title,
    p.abstract = $abstract,
    p.comments = $comments,
    p.doi = $doi,
    p.license = $license,
    p.update_date = CASE
        WHEN $update_date IS NULL THEN null ELSE date($update_date)
    END,
    p.first_submitted_at = CASE
        WHEN $first_submitted_at IS NULL THEN null
        ELSE datetime($first_submitted_at)
    END,
    p.latest_version = $latest_version,
    p.version_count = $version_count,
    p.source = $source

CALL (p) {
    UNWIND $authors AS author
    MERGE (a:Author {author_id: author.author_id})
    SET a.display_name = author.display_name,
        a.family_name = author.family_name,
        a.given_names = author.given_names,
        a.suffix = author.suffix,
        a.normalized_name = author.normalized_name
    MERGE (a)-[authored:AUTHORED]->(p)
    SET authored.position = author.position
    RETURN count(*) AS authors_upserted
}

CALL (p) {
    UNWIND $categories AS category
    MERGE (c:Category {code: category.code})
    MERGE (p)-[in_category:IN_CATEGORY]->(c)
    SET in_category.position = category.position,
        in_category.primary = category.primary
    RETURN count(*) AS categories_upserted
}

CALL (p) {
    UNWIND $versions AS version
    MERGE (v:Version {version_id: version.version_id})
    SET v.version_number = version.version_number,
        v.label = version.label,
        v.created_at = CASE
            WHEN version.created_at IS NULL THEN null
            ELSE datetime(version.created_at)
        END
    MERGE (p)-[:HAS_VERSION]->(v)
    RETURN count(*) AS versions_upserted
}

CALL (p) {
    UNWIND CASE WHEN $submitter IS NULL THEN [] ELSE [$submitter] END AS submitter
    MERGE (s:Submitter {submitter_id: submitter.submitter_id})
    SET s.name = submitter.name,
        s.normalized_name = submitter.normalized_name
    MERGE (s)-[submitted:SUBMITTED]->(p)
    SET submitted.submitted_at = CASE
            WHEN $first_submitted_at IS NULL THEN null
            ELSE datetime($first_submitted_at)
        END,
        submitted.source = $source
    RETURN count(*) AS submitters_upserted
}

CALL (p) {
    UNWIND CASE WHEN $journal IS NULL THEN [] ELSE [$journal] END AS journal
    MERGE (j:Journal {journal_id: journal.journal_id})
    SET j.name = journal.name,
        j.normalized_name = journal.normalized_name
    MERGE (p)-[published:PUBLISHED_IN]->(j)
    SET published.journal_reference_raw = journal.journal_reference_raw,
        published.doi = $doi
    RETURN count(*) AS journals_upserted
}

CALL (p) {
    UNWIND CASE WHEN $report IS NULL THEN [] ELSE [$report] END AS report
    MERGE (r:TechnicalReport {report_number: report.report_number})
    MERGE (p)-[:HAS_REPORT]->(r)
    RETURN count(*) AS reports_upserted
}

RETURN p.arxiv_id AS arxiv_id
"""
