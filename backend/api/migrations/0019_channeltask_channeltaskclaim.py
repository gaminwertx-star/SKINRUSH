# Generated manually (Django unavailable in the editing sandbox)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0018_broadcastmessage'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChannelTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('link', models.URLField(max_length=300)),
                ('reward', models.PositiveIntegerField(default=500)),
                ('sort_order', models.IntegerField(db_index=True, default=0)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ChannelTaskClaim',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('claimed_at', models.DateTimeField(auto_now_add=True)),
                ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='channel_claims', to='api.player')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='claims', to='api.channeltask')),
            ],
        ),
        migrations.AddConstraint(
            model_name='channeltaskclaim',
            constraint=models.UniqueConstraint(fields=('player', 'task'), name='unique_player_channel_task'),
        ),
    ]
