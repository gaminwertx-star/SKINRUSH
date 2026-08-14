# Generated manually (Django unavailable in the editing sandbox)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_promoredemption_drop_unique'),
    ]

    operations = [
        migrations.CreateModel(
            name='Partner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('balance', models.BigIntegerField(default=0)),
                ('total_earned', models.BigIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('player', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='partner', to='api.player')),
                ('promo', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='partner', to='api.promocode')),
            ],
        ),
        migrations.CreateModel(
            name='PartnerEarning',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_sum', models.BigIntegerField()),
                ('commission', models.BigIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('partner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='earnings', to='api.partner')),
                ('referred', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='partner_purchases', to='api.player')),
                ('topup', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='partner_earning', to='api.topuprequest')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PartnerWithdrawRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.BigIntegerField()),
                ('status', models.CharField(choices=[('waiting', "Kutilmoqda"), ('paid', "To'landi")], db_index=True, default='waiting', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('partner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='withdraw_requests', to='api.partner')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
