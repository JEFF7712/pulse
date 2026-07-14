{
  description = "Pulse – personal intelligence system";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        # pyproject requires >=3.12; match nixpkgs’ 3.12 or 3.13 as you prefer
        python = pkgs.python313;
        pythonPkgs = python.pkgs;
        jdk = pkgs.jdk17;
        # Linux desktop target + native engine bits (optional; mobile dev does not require GTK)
        linuxFlutterNative = pkgs.lib.optionals pkgs.stdenv.isLinux [
          pkgs.pkg-config
          pkgs.clang
          pkgs.cmake
          pkgs.ninja
          pkgs.gtk3
          pkgs.glib
        ];
        # Flutter/JDK are multi-GB; keep them out of the default shell.
        companionShell = pkgs.mkShell {
          packages = [
            python
            pkgs.uv
            pythonPkgs.venvShellHook
            pkgs.flutter
            jdk
          ]
          ++ linuxFlutterNative;

          venvDir = ".venv";
          JAVA_HOME = "${jdk}";

          postVenvCreation = ''
            export UV_PYTHON="${python}/bin/python"
            uv sync --group dev
          '';

          postShellHook = ''
            export UV_PYTHON="${python}/bin/python"
            uv sync --group dev --quiet
          '';

          buildInputs = with pkgs; [
            sqlite
          ];

          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath (
            [
              pkgs.stdenv.cc.cc.lib
              pkgs.sqlite
            ]
            ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
              pkgs.gtk3
              pkgs.glib
            ]
          );
        };
      in
      {
        # Default: Python agent only (no Flutter / Android toolchain)
        devShells.default = pkgs.mkShell {
          packages = [
            python
            pkgs.uv
            pythonPkgs.venvShellHook
          ];

          venvDir = ".venv";

          # Install from uv.lock + pyproject (includes dependency-groups.dev → pytest)
          postVenvCreation = ''
            export UV_PYTHON="${python}/bin/python"
            uv sync --group dev
          '';

          postShellHook = ''
            export UV_PYTHON="${python}/bin/python"
            uv sync --group dev --quiet
          '';

          # Native libs some wheels need at build time
          buildInputs = with pkgs; [
            sqlite
          ];

          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.stdenv.cc.cc.lib
            pkgs.sqlite
          ];
        };

        # companion_app/ — dart, flutter, pub, flutter test / run, JDK for Android Gradle
        # Usage: nix develop .#companion
        devShells.companion = companionShell;

        packages.default = pythonPkgs.buildPythonApplication {
          pname = "pulse-agent";
          version = "1.0.0";
          pyproject = true;
          src = ./.;
          nativeBuildInputs = [ pythonPkgs.setuptools ];
          propagatedBuildInputs = with pythonPkgs; [
            rich
            rich-argparse
            fastapi
            pydantic
            aiosqlite
            apscheduler
            httpx
            mcp
            google-auth-oauthlib
            google-api-python-client
            uvicorn
            plaid-python
          ];
        };

        apps.pulse = flake-utils.lib.mkApp {
          drv = self.packages.${system}.default;
          exePath = "/bin/pulse";
        };
      }
    );
}
