# Generated manually (Django unavailable in the editing sandbox)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0017_player_telegram_task_claimed'),
    ]

    operations = [
        migrations.CreateModel(
            name='BroadcastMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(blank=True)),
                ('image', models.FileField(blank=True, null=True, upload_to='broadcasts/%Y/%m/')),
                ('audience', models.CharField(choices=[('all', "Barcha foydalanuvchilar"), ('active', "Faol foydalanuvchilar")], default='all', max_length=16)),
                ('recipients', models.IntegerField(default=0)),
                ('delivered', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('sent_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
