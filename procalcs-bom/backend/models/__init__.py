# Models package
#
# Importing the model modules here ensures SQLAlchemy sees their table
# declarations before Alembic introspects metadata. Don't add anything
# that depends on app context — these import at module load time.

from .user import User                    # noqa: F401
from .subscription_event import SubscriptionEvent  # noqa: F401
from .bom_run import BomRun                # noqa: F401
from .bom_comparison import BomComparison  # noqa: F401
from .discovered_mapping import DiscoveredMapping  # noqa: F401
from .contractor_override import ContractorOverride  # noqa: F401
from .rup_duct_totals import RupDuctTotals  # noqa: F401
from .usage_event import UsageEvent        # noqa: F401
