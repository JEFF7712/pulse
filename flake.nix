{
  description = "Pulse – personal intelligence system";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python313;
        pythonPkgs = python.pkgs;
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            # Python with pip available inside the venv
            python
            pythonPkgs.venvShellHook
          ];

          venvDir = ".venv";

          postVenvCreation = ''
            pip install -e ".[dev]" 2>/dev/null || pip install -e .
          '';

          postShellHook = ''
            # Re-sync if deps changed since last shell entry
            pip install -e . --quiet 2>/dev/null
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
      }
    );
}
