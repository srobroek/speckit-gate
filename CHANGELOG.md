# Changelog

## [0.2.2](https://github.com/srobroek/speckit-gate/compare/speckit-gate-v0.2.1...speckit-gate-v0.2.2) (2026-07-07)


### Features

* **cli:** aligned propose table for terminal; --format md for piping ([51e6bbe](https://github.com/srobroek/speckit-gate/commit/51e6bbe327f64f39c54cd89c9c8220e717e89d98))


### Bug Fixes

* **cli:** dry-run error messages; next-step guidance after init/compile ([4e5a04e](https://github.com/srobroek/speckit-gate/commit/4e5a04e567d8f64cb8069b712de28bd154911d70))
* **hooks:** restore UserPromptExpansion as the user-channel gate ([b082889](https://github.com/srobroek/speckit-gate/commit/b08288944342c1a9ac026f0eaf702b82fc940b8d))


### Performance Improvements

* **dispatch:** fast-path exit for non-speckit events; TTY stdin guard ([2fddcc3](https://github.com/srobroek/speckit-gate/commit/2fddcc3ee0482345a6a66aaaa6daf1876e3f384c))

## [0.2.1](https://github.com/srobroek/speckit-gate/compare/speckit-gate-v0.2.0...speckit-gate-v0.2.1) (2026-07-07)


### Bug Fixes

* **scan:** discover directory-layout skills and extension commands ([fac312f](https://github.com/srobroek/speckit-gate/commit/fac312f4fdd89e64c0eaff2916e2a790b4fec4e8))

## [0.2.0](https://github.com/srobroek/speckit-gate/compare/speckit-gate-v0.1.0...speckit-gate-v0.2.0) (2026-07-07)


### ⚠ BREAKING CHANGES

* **presets:** core preset ships only verified spec-kit built-ins

### Features

* add CI, release-please, and README ([dd35357](https://github.com/srobroek/speckit-gate/commit/dd35357e685fc795e3489633b5191dd656369b34))
* add core preset and JSON schema ([fab5d1d](https://github.com/srobroek/speckit-gate/commit/fab5d1d99f224fd2e0f34d2f5e376c681dd46720))
* add harness adapters and agent skill ([e7f527f](https://github.com/srobroek/speckit-gate/commit/e7f527fa0d1085b3cdcd5de4a27735743c61dffb))
* add stdlib-only runtime modules ([c727a49](https://github.com/srobroek/speckit-gate/commit/c727a49f9020a5c953befa10b256437ce70cc44a))
* add test suite (70 tests, all passing) ([e2b096d](https://github.com/srobroek/speckit-gate/commit/e2b096dd93e2fbcf4c6661bacd7bb225f40acd68))
* initial project scaffold ([84ce637](https://github.com/srobroek/speckit-gate/commit/84ce6378b782ef7fffddae41b21c297cc4ea40dc))
* **pkg:** ship adapter hooks.json inside the package for importlib.resources loading ([f60ca87](https://github.com/srobroek/speckit-gate/commit/f60ca87308a64e592638b6b017e93ea1c3203df5))
* **presets:** core preset ships only verified spec-kit built-ins ([c911607](https://github.com/srobroek/speckit-gate/commit/c9116072bb5d3fa0920191180637784a1fd3edb6))


### Bug Fixes

* **adapters:** rename UserPromptExpansion to UserPromptSubmit; template command as {SPECKIT_GATE_CMD} ([e3aaa67](https://github.com/srobroek/speckit-gate/commit/e3aaa67746eb40f1e1d42906d5939360292fa587))
* **dispatch:** gate Claude Agent-tool spawns via subagent_type ([d70575f](https://github.com/srobroek/speckit-gate/commit/d70575f9657aa5d7b2850c8d5640677751a80a23))
* **install:** importlib.resources adapter loading, settings.json deep-merge, resolved gate command ([0c58481](https://github.com/srobroek/speckit-gate/commit/0c5848179a2ccf657ecadcc22eca5eea672c9fc3))


### Documentation

* **bundle:** drop Amp from harness example lists ([259d9d7](https://github.com/srobroek/speckit-gate/commit/259d9d7f27cd06cb74df6fb0c08317df13e532db))
* drop Amp from the harness matrix ([0b402bb](https://github.com/srobroek/speckit-gate/commit/0b402bb8d5356d680b78d5fb902c9e8f0367bb16))
* per-channel harness enforcement matrix (source-verified) ([7d5e44c](https://github.com/srobroek/speckit-gate/commit/7d5e44ce595a56d1a3a17d47b230e428f7a9f5cd))
