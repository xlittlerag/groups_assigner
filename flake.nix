{
  description = "Python Development Environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = {
    self,
    nixpkgs,
  }: let
    pkgs = import nixpkgs {inherit system;};
    system = "x86_64-linux";
  in {
    devShells."${system}".default = pkgs.mkShell {
      packages = with pkgs; [
        uv
        python3
      ];

      shellHook = ''
        exec zsh
      '';
    };
  };
}
