import uuid

from django.db import models
from django.db import transaction
from django.conf import settings
import redis




class Product(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def check_stock_available(self, quantity):
        return self.stock >= quantity

    @classmethod
    def get_from_cache(cls, product_id):
        r = redis.Redis.from_url(settings.REDIS_URL)
        cache_key = f"product:{product_id}"
        product_data = r.hgetall(cache_key)
        if product_data:
            product = cls()
            product.id = int(product_id)
            product.name = product_data[b'name'].decode('utf-8')
            product.price = float(product_data[b'price'])
            product.stock = int(product_data[b'stock'])
            return product
        return None

    def update_cache(self):
        r = redis.Redis.from_url(settings.REDIS_URL)
        cache_key = f"product:{self.id}"
        product_data = {
            'name': self.name,
            'price': str(self.price),
            'stock': self.stock,
            'is_active': str(self.is_active)
        }
        r.hmset(cache_key, product_data)# 将数据存储到 Redis 中
        r.expire(cache_key, 3600)  # 缓存1小时

    def delete_from_cache(self):
        r = redis.Redis.from_url(settings.REDIS_URL)
        cache_key = f"product:{self.id}"
        r.delete(cache_key)

def generate_order_number():
    """生成唯一的订单号,使用UUID的前8个字符作为订单号"""

    return f"ORD-{uuid.uuid4().hex[:8].upper()}"
class Order(models.Model):
    ORDER_STATUS_PENDING = 'pending'
    ORDER_STATUS_SUCCESS = 'success'
    ORDER_STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (ORDER_STATUS_PENDING, 'Pending'),
        (ORDER_STATUS_SUCCESS, 'Success'),
        (ORDER_STATUS_FAILED, 'Failed'),
    ]

    order_number = models.CharField(
        max_length=50,
        unique=True,
        default=generate_order_number,  # 设置默认值为生成函数
        editable=False,  # 不可编辑
        db_index=True  # 添加索引
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ORDER_STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Order.STATUS_CHOICES, default=Order.ORDER_STATUS_PENDING)
    failure_reason = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.product.name} x {self.quantity} in {self.order.order_number}"
