from pxr import Usd
import sys

def removeProperty(filePath, mtlShaderPath, mtlPropertyToken):
    stage = Usd.Stage.Open(filePath)
    mtlPrim = stage.GetObjectAtPath(mtlShaderPath)
    mtlProperty = mtlPrim.GetProperty("inputs:" + mtlPropertyToken)
    connections = mtlProperty.GetConnections()
    # if len(connections) > 0:
    #     for connection in connections:
    #         texturePrim = connection.GetPrimPath()
    #         stage.RemovePrim(texturePrim)
    mtlPrim.RemoveProperty("inputs:" + mtlPropertyToken)
    stage.GetRootLayer().Save()
    stage = None

if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) < 3:
        print("Arguments must include path to USD file, material path, and property to remove.")
        exit()
    filePath = args[0]
    mtlShaderPath = args[1]
    mtlPropertyToken = args[2]
    removeProperty(filePath, mtlShaderPath, mtlPropertyToken)
