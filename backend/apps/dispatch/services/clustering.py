"""Turn many reports of ONE emergency into ONE job.

WHY THIS EXISTS
---------------
Five neighbours watching the same embankment go each press SOS. That is five
Incident rows, and it has to stay five rows: each one is a real person we may
need to call back, and the corroboration count is only meaningful because they
are separate records.

But it is ONE flood, and the solver was being handed it as five independent
jobs. Measured on the seeded Sakhigopal scenario -- one breach, 42 people, five
callers -- the optimiser sent FIVE separate boats, one per report row.

The damage is worse than the wasted hulls. engine.build_demand_slots already has
the mechanism that is supposed to stop exactly this: a scene needing several
units gets several slots, and each extra slot is worth MARGINAL_SLOT_DECAY less
than the last, so the third boat to one village loses to the first boat to the
next village. That decay never fired, because every duplicate row arrived as a
fresh incident at slot 0 with its full priority. The anti-dogpile rule was
switched off by the shape of the input.

Clustering here restores it. One job for the cell, people summed, so the solver
asks for ceil(42/12) = 4 slots with proper decay instead of 5 undecayed ones.

WHY cell_id AND kind
--------------------
cell_id is the same two-decimal (~1.1 km) bucket the corroboration count and the
dashboard's grouping already use, so all three agree on what "the same place"
means. kind is in the key because a flood and a landslide at the same crossroads
need different capabilities and genuinely are two jobs -- merging them would
produce a demand no single unit can serve.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Job:
    """One scene. Usually one report; sometimes half a village."""
    key: str                     # "19.93,85.84|FLOOD" -- the engine's incident id
    members: List = field(default_factory=list)   # every Incident row, oldest first

    @property
    def primary(self):
        """The row that names the job.

        Oldest first, so the label does not jump around as more people call in.
        This is the same rule the dashboard's groupByArea uses, and it has to
        stay the same or the operator sees one code on the map and another in
        the dispatch list.
        """
        return self.members[0]

    @property
    def lat(self):
        return sum(m.lat for m in self.members) / len(self.members)

    @property
    def lon(self):
        return sum(m.lon for m in self.members) / len(self.members)

    @property
    def kind(self):
        return self.primary.kind

    @property
    def severity(self):
        """The worst thing anyone reported. Averaging would let four calm
        callers talk over the one person who can see the roof coming down."""
        return max(m.severity for m in self.members)

    @property
    def people(self):
        """Summed, because the seed splits a village's headcount across its
        callers. This is the number the slot count is computed from."""
        return sum(m.people for m in self.members)

    @property
    def corroborations(self):
        return max(m.corroborations or 1 for m in self.members)

    @property
    def reported_at(self):
        """The FIRST call, so the age term measures how long the village has
        been waiting -- not how recently the last person redialled."""
        return min(m.reported_at for m in self.members)


def cluster_incidents(incidents):
    """[Incident] -> [Job], worst and oldest first.

    Rows with no cell_id fall back to their own primary key, so a report that
    somehow arrived without one becomes a job of one rather than merging with
    every other cell-less row in the district.
    """
    jobs = {}
    for incident in incidents:
        key = f"{incident.cell_id or f'inc:{incident.pk}'}|{incident.kind}"
        jobs.setdefault(key, Job(key=key)).members.append(incident)

    for job in jobs.values():
        job.members.sort(key=lambda i: (i.reported_at, i.pk))

    return sorted(jobs.values(), key=lambda j: (-j.severity, j.reported_at))
