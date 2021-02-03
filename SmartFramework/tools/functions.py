def cached_one_arg_func(user_function):
    sentinel = object()  # unique object used to signal cache misses
    cache = {}
    cache_get = cache.get

    def wrapper(key):
        result = cache_get(key, sentinel)
        if result is not sentinel:
            return result
        result = user_function(key)
        cache[key] = result
        return result

    return wrapper
