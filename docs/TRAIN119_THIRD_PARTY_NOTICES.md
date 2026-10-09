# Third-party boundaries

The selected diagnostic payload deliberately excludes Quantum ESPRESSO and MLIP
executables, pseudopotential binaries, fonts, and heavy scratch. Saved project
inputs/outputs are not described as a redistribution of those executables.

The inspected MLIP source copy identifies itself under the BSD 2-Clause license,
copyright 2023 Alexander Shapeev(Skoltech). Preserve the complete upstream notice
when publishing the narrow `IO_ONLY.patch` or relevant source excerpts. The source
notice is reproduced below; it does not relicense other components as BSD or MIT.

The PSLibrary project page states GNU General Public License terms for the project.
This is not a file-by-file legal audit of the particular UPF distribution. Omitting
UPF from the compact arithmetic payload avoids an unnecessary distribution dependency.
The project's own code/data license declarations must remain separate from third-party
notices. No new legal ownership claim is made by this audit.

## MLIP source notice

BSD 2-Clause License

Copyright (c) 2023, Alexander Shapeev (Skoltech)

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
