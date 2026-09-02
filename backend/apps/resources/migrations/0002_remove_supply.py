"""Drop the supply-chain models. Dropping the unique_together has to come
before dropping the field it names, or Django cannot resolve it."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0001_initial"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="supplystock",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="supplystock",
            name="depot",
        ),
        migrations.DeleteModel(name="SupplyStock"),
        migrations.DeleteModel(name="Depot"),
    ]
