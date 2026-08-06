from django.db import migrations, models


#: Old Tetun/Portuguese stored values -> new English ones. The labels users
#: see stay Tetun; only the machine value changes.
MAPA = {
    'PREZENTE': 'PRESENT',
    'FALTA': 'ABSENT',
    'LISENSA': 'LEAVE',
    'MISAUN': 'MISSION',
    'FERIADU': 'HOLIDAY',
}


def ba_ingles(apps, schema_editor):
    Prezensa = apps.get_model('attendance', 'Prezensa')
    for tuan, foun in MAPA.items():
        Prezensa.objects.filter(status=tuan).update(status=foun)


def ba_tetun(apps, schema_editor):
    Prezensa = apps.get_model('attendance', 'Prezensa')
    for tuan, foun in MAPA.items():
        Prezensa.objects.filter(status=foun).update(status=tuan)


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0002_remove_prezensa_foto_dader_fila_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='prezensa',
            old_name='estadu',
            new_name='status',
        ),
        migrations.AlterField(
            model_name='prezensa',
            name='status',
            field=models.CharField(
                choices=[
                    ('PRESENT', 'Prezente'),
                    ('ABSENT', 'Falta'),
                    ('LEAVE', 'Lisensa'),
                    ('MISSION', 'Misaun'),
                    ('HOLIDAY', 'Feriadu'),
                ],
                default='PRESENT',
                max_length=10,
                verbose_name='status',
            ),
        ),
        migrations.RunPython(ba_ingles, ba_tetun),
    ]
