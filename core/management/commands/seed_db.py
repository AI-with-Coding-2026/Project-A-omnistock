from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from faker import Faker
from inventory.models import Product, PurchaseOrder, PurchaseOrderItem, Supplier
from orders.models import Order, OrderItem


class Command(BaseCommand):
    help = (
        "Creates or refreshes repeatable development demo data: users, "
        "suppliers, products, and orders."
    )

    DEMO_PASSWORD = "demo12345"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow seeding when DEBUG=False.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_db is only available when DEBUG=True. "
                "Use --force if you really want to run it."
            )
            
        fake = Faker()
        Faker.seed(20260825)

        with transaction.atomic():
            users = self.seed_users()
            suppliers = self.seed_suppliers(fake)
            products = self.seed_products(fake, suppliers)
            orders = self.seed_orders(fake, users, products)
            supplier_users = self.seed_supplier_users(suppliers)
            purchase_orders = self.seed_purchase_orders(users, suppliers, products)

        low_stock_count = Product.low_stock().count()

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data ready: "
                f"{len(users)} users, "
                f"{len(suppliers)} suppliers, "
                f"{len(products)} products "
                f"({low_stock_count} low-stock), "
                f"{len(orders)} orders, "
                f"{len(supplier_users)} supplier portal accounts, "
                f"{len(purchase_orders)} purchase orders."
            )
        )
        self.stdout.write(
            "Demo login: admin / demo12345"
        )
        self.stdout.write(
            "Supplier portal demo logins: supplier_portal_1 / demo12345, supplier_portal_2 / demo12345"
        )

    def seed_users(self):
        User = get_user_model()

        demo_users = [
            {
                "username": "admin",
                "email": "admin@omnistock.demo",
                "first_name": "Alex",
                "last_name": "Admin",
                "role": User.ROLE_ADMIN,
            },
            {
                "username": "sales_rep",
                "email": "sales@omnistock.demo",
                "first_name": "Sam",
                "last_name": "Sales",
                "role": User.ROLE_SALES_REP,
            },
            {
                "username": "inventory_manager",
                "email": "inventory@omnistock.demo",
                "first_name": "Morgan",
                "last_name": "Inventory",
                "role": User.ROLE_INVENTORY_MANAGER,
            },
            {
                "username": "staff",
                "email": "staff@omnistock.demo",
                "first_name": "Taylor",
                "last_name": "Staff",
                "role": User.ROLE_STAFF,
            },
        ]

        users = []

        for data in demo_users:
            user, _ = User.objects.get_or_create(
                username=data["username"],
                defaults=data,
            )

            user.email = data["email"]
            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.role = data["role"]
            user.is_active = True
            user.set_password(self.DEMO_PASSWORD)
            user.save()

            users.append(user)

        return users

    def seed_suppliers(self, fake):
        suppliers = []

        for number in range(1, 11):
            supplier, _ = Supplier.objects.update_or_create(
                email=f"supplier{number}@omnistock.demo",
                defaults={
                    "name": f"{fake.company()}",
                    # E.164-style demo phone number
                    "phone": f"+1{fake.numerify('##########')}",
                    "address": fake.address(),
                },
            )
            suppliers.append(supplier)

        return suppliers

    def seed_products(self, fake, suppliers):
        products = []

        product_types = [
            "Wireless Keyboard",
            "Mechanical Keyboard",
            "USB-C Cable",
            "Laptop Stand",
            "Office Chair",
            "Printer Paper",
            "Desk Lamp",
            "Wireless Mouse",
            "Webcam",
            "Monitor Arm",
        ]

        for number in range(1, 41):
            reorder_level = 10 + (number % 4) * 5

            # Every fifth product is intentionally at/below its reorder level.
            if number % 5 == 0:
                stock_quantity = max(0, reorder_level - (number % 6))
            else:
                stock_quantity = reorder_level + 20 + (number * 2)

            product_name = (
                f"{product_types[(number - 1) % len(product_types)]} "
                f"Model {number:02d}"
            )

            product, _ = Product.objects.update_or_create(
                sku=f"DEMO-SKU-{number:04d}",
                defaults={
                    "supplier": suppliers[(number - 1) % len(suppliers)],
                    "name": product_name,
                    "description": fake.sentence(nb_words=14),
                    "unit_price": Decimal(str(round(fake.pydecimal(
                        left_digits=3,
                        right_digits=2,
                        positive=True,
                        min_value=Decimal("5.00"),
                        max_value=Decimal("450.00"),
                    ), 2))),
                    "stock_quantity": stock_quantity,
                    "reorder_level": reorder_level,
                },
            )
            products.append(product)

        return products

    def seed_supplier_users(self, suppliers):
        """
        Links the first two demo suppliers to Supplier-role portal accounts,
        so the isolation between suppliers can be demonstrated out of the box.
        """
        User = get_user_model()

        demo_supplier_logins = [
            {
                "username": "supplier_portal_1",
                "email": "supplier-portal-1@omnistock.demo",
                "first_name": "Priya",
                "last_name": "Vendor",
            },
            {
                "username": "supplier_portal_2",
                "email": "supplier-portal-2@omnistock.demo",
                "first_name": "Chen",
                "last_name": "Vendor",
            },
        ]

        supplier_users = []

        for supplier, data in zip(suppliers[:2], demo_supplier_logins):
            user, _ = User.objects.get_or_create(
                username=data["username"],
                defaults={**data, "role": User.ROLE_SUPPLIER},
            )
            user.email = data["email"]
            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.role = User.ROLE_SUPPLIER
            user.is_active = True
            user.set_password(self.DEMO_PASSWORD)
            user.save()

            supplier.user = user
            supplier.save(update_fields=["user"])

            supplier_users.append(user)

        return supplier_users

    def seed_purchase_orders(self, users, suppliers, products):
        """
        Creates a pending PO for each of the first two demo suppliers, so the
        supplier portal has something to accept/reject out of the box.
        """
        admin_user = next(u for u in users if u.username == "admin")
        purchase_orders = []

        for number, supplier in enumerate(suppliers[:2], start=1):
            po_number = f"DEMO-PO-{number:04d}"
            po, _ = PurchaseOrder.objects.update_or_create(
                po_number=po_number,
                defaults={
                    "supplier": supplier,
                    "created_by": admin_user,
                    "status": PurchaseOrder.STATUS_PENDING,
                },
            )

            po.items.all().delete()

            product = products[(number - 1) % len(products)]
            PurchaseOrderItem.objects.create(
                purchase_order=po,
                product=product,
                quantity=5 + number,
                unit_cost=product.unit_price,
            )

            purchase_orders.append(po)

        return purchase_orders

    def seed_orders(self, fake, users, products):
        orders = []

        statuses = [
            Order.STATUS_PENDING,
            Order.STATUS_COMPLETED,
            Order.STATUS_CANCELLED,
        ]

        for number in range(1, 31):
            status = statuses[(number - 1) % len(statuses)]
            order_number = f"DEMO-ORD-{number:04d}"

            order = Order.objects.filter(order_number=order_number).first()

            if order is None:
                order = Order.objects.create(
                    order_number=order_number,
                    user=users[(number - 1) % len(users)],
                    customer_name=fake.name(),
                    status=status,
                    total_amount=Decimal("0.00"),
                )
            else:
                Order.objects.filter(pk=order.pk).update(
                    user=users[(number - 1) % len(users)],
                    customer_name=fake.name(),
                    status=status,
                    total_amount=Decimal("0.00"),
                )
                order.refresh_from_db()

            # These are only demo orders identified by DEMO-ORD-xxxx.
            # Replacing their items keeps reruns idempotent.
            order.items.all().delete()

            selected_products = [
                products[(number * 2) % len(products)],
                products[(number * 2 + 7) % len(products)],
            ]

            total_amount = Decimal("0.00")

            for index, product in enumerate(selected_products, start=1):
                quantity = (number + index) % 4 + 1
                unit_price = product.unit_price
                total_amount += unit_price * quantity

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                )

            order.total_amount = total_amount
            order.save(update_fields=["total_amount", "updated_at"])

            # Make the list/dashboard feel historical rather than all-new.
            Order.objects.filter(pk=order.pk).update(
                created_at=timezone.now() - timedelta(days=number * 3)
            )

            orders.append(order)

        return orders