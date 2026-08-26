"""Human-readable row codes: INC0142, ASG0088, RES0007.

Used by reports (INC) and dispatch (ASG). Kept in common/ so neither app has to
import the other just to number a row.
"""


def next_code(prefix, model=None, field="code", width=4):
    """Allocate the next sequential code for a model.

    IN:
      prefix = str          # "INC" | "ASG" | "RES" | "SHL" | "DEP"
      model  = django.db.models.Model subclass | None
               # the table to scan for the current maximum. None -> caller must
               # pass one; there is no global counter.
      field  = str          # column holding the code, default "code"
      width  = int          # zero-pad width, default 4 -> "INC0142"

    OUT:
      str                   # "INC0143" -- prefix + zero-padded (max + 1)

    DB:
      SELECT <field> FROM <model table> WHERE <field> LIKE '<prefix>%'
        ORDER BY <field> DESC LIMIT 1        -- <field> is unique, so indexed
      Then INSERT is the caller's job.

    NOTE for whoever implements this:
      The read-then-write is racy under concurrent POSTs. Two options, pick one:
        a) call this INSIDE transaction.atomic() and retry once on IntegrityError
           (the unique constraint on `code` is the real guard), or
        b) back it with a Postgres sequence per prefix.
      (a) is fine at hackathon scale and is three lines shorter.
    """
    if model is None:
        raise ValueError("next_code needs the model whose table holds the codes")

    last = (model.objects
            .filter(**{f"{field}__startswith": prefix})
            .order_by(f"-{field}")
            .values_list(field, flat=True)
            .first())

    n = 0
    if last:
        digits = last[len(prefix):]
        if digits.isdigit():
            n = int(digits)
    return f"{prefix}{n + 1:0{width}d}"