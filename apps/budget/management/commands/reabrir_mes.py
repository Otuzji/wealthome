"""Reabre un mes cerrado para volver a cerrarlo con el reparto decidido.

Existe por el cierre de octubre de 2026 del piloto, hecho con la regla vieja:
la mesada concedida al planificar no se retiraba, el faltante bajaba como
ajuste negativo a la mesada del mes siguiente, y el arrastre no descontaba lo
repartido. Deshace exactamente lo que ese cierre escribio:

- el MonthlyClose del mes,
- los aportes de la cascada a las metas con fecha de ese mes,
- lo real de cada reparto del mes (`actual_amount`),
- los ajustes que el cierre dejo en las mesadas del mes siguiente,

y deja el mes abierto. Solo el ULTIMO mes cerrado: con uno posterior cerrado,
su arrastre ya dependeria de este. Sin --aplicar solo cuenta lo que haria.

Las cadenas no pasan por gettext a proposito: es una herramienta de
mantenimiento, en el idioma de quien la corre, no una pantalla.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.budget import services_goals
from apps.budget.models import (
    AllowanceLedger, BudgetMonth, GoalContribution, MonthlyAllocation, MonthlyClose,
)
from apps.budget.services import mes_siguiente


class Command(BaseCommand):
    help = "Reabre el ultimo mes cerrado de un hogar (por defecto, solo informa)."

    def add_arguments(self, parser):
        parser.add_argument("--hogar", type=int, required=True)
        parser.add_argument("--anio", type=int, required=True)
        parser.add_argument("--mes", type=int, required=True)
        parser.add_argument(
            "--saldo-inicial", help="Si el mes no tiene saldo inicial anotado, este "
            "(p. ej. 0): asi el cierre no hereda el arrastre del mes anterior.",
        )
        parser.add_argument("--aplicar", action="store_true",
                            help="Escribe los cambios. Sin esto, solo informa.")

    def handle(self, *args, **o):
        mes = BudgetMonth.unscoped.filter(
            household_id=o["hogar"], year=o["anio"], month=o["mes"],
        ).first()
        if mes is None:
            raise CommandError("Ese mes no existe en ese hogar.")
        cierre = MonthlyClose.unscoped.filter(budget_month=mes).first()
        if mes.status != BudgetMonth.CLOSED or cierre is None:
            raise CommandError(f"{mes} no esta cerrado.")
        posteriores = MonthlyClose.unscoped.filter(household_id=o["hogar"]).filter(
            Q(budget_month__year__gt=mes.year)
            | Q(budget_month__year=mes.year, budget_month__month__gt=mes.month)
        )
        if posteriores.exists():
            raise CommandError("Hay un mes posterior cerrado: reabrir este rompe su arrastre.")

        aportes = GoalContribution.unscoped.filter(budget_month=mes, origen="cascade")
        repartos = MonthlyAllocation.unscoped.filter(budget_month=mes)
        anio_sig, mes_sig = mes_siguiente(mes.year, mes.month)
        ajustes = AllowanceLedger.unscoped.filter(
            household_id=o["hogar"], budget_month__year=anio_sig,
            budget_month__month=mes_sig,
        ).exclude(adjustment=Decimal("0.00"))

        self.stdout.write(
            f"{mes}: cierre con balance {cierre.balance} y arrastre {cierre.arrastre}."
        )
        for a in aportes:
            self.stdout.write(f"  aporte de la cascada a {a.goal}: {a.amount}")
        for r in repartos:
            self.stdout.write(
                f"  reparto regla {r.rule_id} miembro {r.member_id}: "
                f"planeado {r.planned_amount}, real {r.actual_amount}"
            )
        for libro in ajustes:
            self.stdout.write(f"  ajuste en la mesada de {libro.member}: {libro.adjustment}")
        nuevo_saldo = None
        if mes.opening_balance is None and o.get("saldo_inicial") is not None:
            nuevo_saldo = Decimal(o["saldo_inicial"])
            self.stdout.write(f"  saldo inicial sin anotar: se anota {nuevo_saldo}")
        else:
            self.stdout.write(f"  saldo inicial: {mes.opening_balance}")

        if not o["aplicar"]:
            self.stdout.write(self.style.WARNING("Sin --aplicar: no se ha tocado nada."))
            return

        with transaction.atomic():
            metas = {a.goal for a in aportes}
            # Primero abrir: la guarda de los meses cerrados para cualquier
            # escritura sobre sus filas. Por queryset, que no pasa por save().
            BudgetMonth.unscoped.filter(pk=mes.pk).update(
                status=BudgetMonth.OPEN, closed_at=None,
                **({"opening_balance": nuevo_saldo} if nuevo_saldo is not None else {}),
            )
            # Por queryset: MonthlyClose.save() se niega a reescribir un cierre.
            MonthlyClose.unscoped.filter(pk=cierre.pk).delete()
            aportes.delete()
            repartos.update(actual_amount=None)
            ajustes.update(adjustment=Decimal("0.00"))
            for meta in metas:
                services_goals.recalcular_estado(meta)
        self.stdout.write(self.style.SUCCESS(f"{mes} reabierto."))
