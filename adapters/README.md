# Adapter extension area

This directory is reserved for optional provider integrations.

The built-in Python provider contract lives in
`power_socket/providers/base.py`. There is no forced transport protocol.

Third-party Python packages can register providers through the
`power_socket.providers` entry-point group. For example, a package can declare:

```toml
[project.entry-points."power_socket.providers"]
my-provider = "my_package.adapter:MyProvider"
```

The referenced class must inherit from `Provider` and implement
`generate(model, messages, endpoint)`. It may also implement `list_models(endpoint)`.
Set the profile's provider field to the entry-point name (`my-provider`).

An adapter can bridge to another language or runtime by using a native library,
a local executable, or a service endpoint inside its Python implementation.
A Rust/C++/Java/JavaScript implementation is not prohibited; only the small
integration bridge needs to satisfy the Python-side provider contract.

Keep provider-specific code isolated. Do not add compiler requirements to the
main application unless a selected adapter actually needs them.
