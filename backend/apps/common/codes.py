"""Human-readable row codes: INC0142, ASG0088.

Used by reports (INC) and dispatch (ASG). Kept in common/ so neither app has to
import the other just to number a row.
"""


def next_code(prefix, model, field="code", width=4):
    """The next sequential code for a model, e.g. next_code("INC", Incident).

    One indexed lookup for the current maximum; the INSERT is the caller's job.
    The read-then-write is racy under concurrent POSTs -- call it inside
    transaction.atomic() and let the unique constraint on `code` be the real
    guard, which is what reports.services.create_incident() does.

    Callers building several UNSAVED rows at once must count up from one call
    rather than calling repeatedly: nothing is committed in between, so every
    call would return the same string. dispatch.services.assign.build_plan does that.
    """
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
