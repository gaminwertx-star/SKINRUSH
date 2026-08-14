# Generated manually (Django unavailable in the editing sandbox)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_channeltask_channeltaskclaim'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='promoredemption',
            name='uniq_promo_per_player',
        ),
    ]
