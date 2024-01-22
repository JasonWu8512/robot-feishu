from kevin.endpoints.management.models import Account


class CommandError(Exception):
    """ 可预期的执行错误 """


def guess_username(name) -> str:
    """ 给个片段，猜他的全名 """
    try:
        return Account.objects.get(name=name).jira_name
    except Account.DoesNotExist:
        pass

    try:
        return Account.objects.get(name__icontains=name).jira_name
    except Account.DoesNotExist:
        pass
    except Account.MultipleObjectsReturned:
        raise CommandError(f"唔好意思，叫 {name} 个人太多啦，你想瘟嗝系边个？")

    try:
        return Account.objects.get(email__icontains=name).jira_name
    except Account.DoesNotExist:
        raise CommandError(f"唔好意思，我真系搵唔到叫 {name} 个人啊")
    except Account.MultipleObjectsReturned:
        raise CommandError(f"唔好意思，叫 {name} 个人太多啦，你想瘟嗝系边个？")
