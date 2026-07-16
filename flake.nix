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

        packages.default = pythonPkgs.buildPythonApplication {
          pname = "pulse-agent";
          version = "3.1.1";
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
    )
    // {
      # NixOS module: run `pulse run` (HTTP server + scheduler) as a systemd service.
      # Add to your system flake and set `services.pulse.enable = true;`. You must place a
      # `pulse.toml` (with your secrets) in `services.pulse.stateDir` first, or run
      # `pulse configure` against that directory — secrets are never put in the Nix store.
      nixosModules.default =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        let
          cfg = config.services.pulse;
        in
        {
          options.services.pulse = {
            enable = lib.mkEnableOption "the Pulse personal-data agent daemon";

            package = lib.mkOption {
              type = lib.types.package;
              default = self.packages.${pkgs.system}.default;
              defaultText = lib.literalExpression "pulse.packages.\${system}.default";
              description = "The pulse-agent package to run.";
            };

            user = lib.mkOption {
              type = lib.types.str;
              default = "pulse";
              description = "User account under which Pulse runs.";
            };

            group = lib.mkOption {
              type = lib.types.str;
              default = "pulse";
              description = "Group under which Pulse runs.";
            };

            stateDir = lib.mkOption {
              type = lib.types.str;
              default = "/var/lib/pulse";
              description = ''
                Directory holding Pulse's config (`pulse.toml`), database, and vault. Secrets
                live here, not in the Nix store. Provision `pulse.toml` here before starting.
              '';
            };

            host = lib.mkOption {
              type = lib.types.str;
              default = "127.0.0.1";
              description = "Address the Pulse HTTP server binds to.";
            };

            port = lib.mkOption {
              type = lib.types.port;
              default = 8000;
              description = "Port for the Pulse HTTP server / operator UI.";
            };

            environment = lib.mkOption {
              type = lib.types.attrsOf lib.types.str;
              default = { };
              example = {
                PULSE_TIMEZONE = "America/Chicago";
              };
              description = "Extra environment variables for the Pulse service.";
            };
          };

          config = lib.mkIf cfg.enable {
            users.users = lib.mkIf (cfg.user == "pulse") {
              pulse = {
                isSystemUser = true;
                group = cfg.group;
                home = cfg.stateDir;
                description = "Pulse agent service user";
              };
            };

            users.groups = lib.mkIf (cfg.group == "pulse") {
              pulse = { };
            };

            systemd.services.pulse = {
              description = "Pulse personal-data agent (HTTP server + scheduler)";
              wantedBy = [ "multi-user.target" ];
              after = [ "network-online.target" ];
              wants = [ "network-online.target" ];

              environment = {
                PULSE_CONFIG_DIR = cfg.stateDir;
                PULSE_DATABASE_PATH = "${cfg.stateDir}/pulse.db";
                PULSE_VAULT_PATH = "${cfg.stateDir}/vault";
              }
              // cfg.environment;

              serviceConfig = {
                ExecStart = "${cfg.package}/bin/pulse run --host ${cfg.host} --port ${toString cfg.port}";
                User = cfg.user;
                Group = cfg.group;
                WorkingDirectory = cfg.stateDir;
                StateDirectory = "pulse";
                Restart = "on-failure";
                RestartSec = 10;
                # Hardening
                NoNewPrivileges = true;
                ProtectSystem = "strict";
                ProtectHome = true;
                ReadWritePaths = [ cfg.stateDir ];
                PrivateTmp = true;
              };
            };
          };
        };
    };
}
