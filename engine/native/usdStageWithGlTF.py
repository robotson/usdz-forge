from pxr import *

import json
import struct
try:
    import numpy
    _HAS_NUMPY = True
except ImportError:
    import numpy_compat as numpy
    _HAS_NUMPY = False


def _pxrVec3fArrayFromAccessor(accessor):
    data = accessor.data
    return Vt.Vec3fArray([
        Gf.Vec3f(float(data[i * 3]), float(data[i * 3 + 1]), float(data[i * 3 + 2]))
        for i in range(accessor.count)
    ])


def _pxrIntArrayFromData(data):
    if _HAS_NUMPY:
        return data
    return Vt.IntArray([int(v) for v in data])
import os.path
import base64

import re

import usdUtils

__all__ = ['usdStageWithGlTF']


def makeValidPrimName(name):
    validated = re.sub('[^A-Za-z0-9_]', '_', name)
    if not validated or validated[0].isdigit():
        validated = '_' + validated
    return validated


class glTFComponentType:
    BYTE = 5120
    UNSIGNED_BYTE = 5121
    SHORT = 5122
    UNSIGNED_SHORT = 5123
    UNSIGNED_INT = 5125
    FLOAT = 5126

    def __init__(self, type):
        self.type = type

    def unpackFormat(self):
        return {
            glTFComponentType.BYTE: numpy.uint8,
            glTFComponentType.UNSIGNED_BYTE: numpy.uint8,
            glTFComponentType.SHORT: numpy.int16,
            glTFComponentType.UNSIGNED_SHORT: numpy.uint16,
            glTFComponentType.UNSIGNED_INT: numpy.uint32,
            glTFComponentType.FLOAT: numpy.float32
            } [self.type]


    def size(self):
        return {
            glTFComponentType.BYTE: 1,
            glTFComponentType.UNSIGNED_BYTE: 1,
            glTFComponentType.SHORT: 2,
            glTFComponentType.UNSIGNED_SHORT: 2,
            glTFComponentType.UNSIGNED_INT: 4,
            glTFComponentType.FLOAT: 4
            } [self.type]        


class glFTTextureFilter: # TODO: support
    NEAREST = 9728
    LINEAR = 9729
    NEAREST_MIPMAP_NEAREST = 9984
    LINEAR_MIPMAP_NEAREST = 9985
    NEAREST_MIPMAP_LINEAR = 9986
    LINEAR_MIPMAP_LINEAR = 9987


class glTFWrappingMode:
    CLAMP_TO_EDGE = 33071
    MIRRORED_REPEAT = 33648
    REPEAT = 10497

    def __init__(self, mode):
        self.mode = mode

    def usdMode(self):
        return {
            glTFWrappingMode.CLAMP_TO_EDGE: 'clamp',
            glTFWrappingMode.MIRRORED_REPEAT: 'mirror',
            glTFWrappingMode.REPEAT: 'repeat'
            } [self.mode]


class gltfPrimitiveMode:
    POINTS = 0
    LINES = 1
    LINE_LOOP = 2
    LINE_STRIP = 3
    TRIANGLES = 4
    TRIANGLE_STRIP = 5
    TRIANGLE_FAN = 6


def loadChunk(file, format):
    size = struct.calcsize(format)
    unpack = struct.Struct(format).unpack_from
    return unpack(file.read(size))


def numOfComponents(strType):
    if strType == 'VEC2':
        return 2
    elif strType == 'VEC3':
        return 3
    elif strType == 'VEC4':
        return 4
    elif strType == 'MAT4':
        return 16
    return 1


def getName(dict, template, id):
    if 'name' in dict and len(dict['name']) != 0:
        validName = usdUtils.makeValidIdentifier(dict['name'])
        if validName != 'defaultIdentifier':
            return validName
    return template + str(id)


def getInt(dict, key):
    if key in dict:
        return dict[key]
    return 0


def getVec3(v):
    return Gf.Vec3d(v[0], v[1], v[2])


def getVec4(v):
    if len(v) == 4:
        return Gf.Vec4d(v[0], v[1], v[2], v[3])
    return Gf.Vec4d(v[0], v[1], v[2], 1)


def getQuat(v):
    return Gf.Quatf(v[3], Gf.Vec3f(v[0], v[1], v[2]))


def getMatrix(m):
    return Gf.Matrix4d((m[0], m[1], m[2], m[3]), (m[4], m[5], m[6], m[7]), (m[8], m[9], m[10], m[11]), (m[12], m[13], m[14], m[15]))


def getMatrixTransform(gltfNode):
    if 'matrix' in gltfNode:
        matrix = getMatrix(gltfNode['matrix'])
    else:
        if 'scale' in gltfNode:
            matrix = Gf.Matrix4d(getVec4(gltfNode['scale']))
        else:
            matrix = Gf.Matrix4d(1)

        if 'rotation' in gltfNode:
            matRot = Gf.Matrix4d()
            matRot.SetRotate(getQuat(gltfNode['rotation']))
            matrix = matrix * matRot

        if 'translation' in gltfNode:
            matTr = Gf.Matrix4d()
            matTr.SetTranslate(getVec3(gltfNode['translation']))
            matrix = matrix * matTr 
    return matrix


def getTransformTranslation(gltfNode):
    if 'translation' in gltfNode:
        translation = gltfNode['translation']
        return Gf.Vec3f(translation[0], translation[1], translation[2])
    else:
        return Gf.Vec3f(0, 0, 0) # TODO: support decomposition?


def getTransformRotation(gltfNode):
    if 'rotation' in gltfNode:
        rotation = gltfNode['rotation']
        return Gf.Quatf(rotation[3], Gf.Vec3f(rotation[0], rotation[1], rotation[2]))
    else:
        return Gf.Quatf(1, Gf.Vec3f(0, 0, 0)) # TODO: support decomposition?


def getTransformScale(gltfNode):
    if 'scale' in gltfNode:
        scale = gltfNode['scale']
        return Gf.Vec3f(scale[0], scale[1], scale[2])
    else:
        return Gf.Vec3f(1, 1, 1) # TODO: support decomposition?


def getInterpolatedValue(timeValueDic, time, isSlerp=False):
    if time in timeValueDic:
        return timeValueDic[time]
    # find neighbor keys for time
    # to get an interpolated value
    lessMaxTime = -1
    greaterMinTime = -1
    for t in timeValueDic:
        if t < time:
            if lessMaxTime == -1:
                lessMaxTime = t
            elif lessMaxTime < t:
                lessMaxTime = t
        elif t > time:
            if greaterMinTime == -1:
                greaterMinTime = t
            elif greaterMinTime > t:
                greaterMinTime = t

    if lessMaxTime == -1:
        return timeValueDic[greaterMinTime]
    if greaterMinTime == -1:
        return timeValueDic[lessMaxTime]

    k = float(time - lessMaxTime) / (greaterMinTime - lessMaxTime)

    if isSlerp:
        q = Gf.Slerp(k, timeValueDic[lessMaxTime], timeValueDic[greaterMinTime])
        i = q.GetImaginary()
        return Gf.Quatf(q.GetReal(), Gf.Vec3f(i[0], i[1], i[2]))

    return timeValueDic[lessMaxTime] * (1-k) + timeValueDic[greaterMinTime] * k


def getXformOp(usdGeom, type):
    ops = usdGeom.GetOrderedXformOps()
    for op in ops:
        if op.GetOpType() == type:
            return op
    return None


def indicesWithTriangleStrip(indices):
    if len(indices) <= 3:
        return indices
    newIndices = [int(indices[0]), int(indices[1]), int(indices[2])]
    for i in range(3, len(indices)):
        newIndices.append(int(indices[i-1]))
        newIndices.append(int(indices[i-2]))
        newIndices.append(int(indices[i]))
    return newIndices


def indicesWithTriangleFan(indices):
    if len(indices) <= 3:
        return indices
    newIndices = []
    for i in range(2, len(indices)):
        newIndices.append(int(indices[0]))
        newIndices.append(int(indices[i-1]))
        newIndices.append(int(indices[i]))
    return newIndices


def getGfVec3fFromData(data, offset):
    return Gf.Vec3f(float(data[offset]), float(data[offset + 1]), float(data[offset + 2]))


def getGfQuatfFromData(data, offset):
    return Gf.Quatf(float(data[offset + 3]), Gf.Vec3f(float(data[offset]), float(data[offset + 1]), float(data[offset + 2])))


class glTFNodeManager(usdUtils.NodeManager):
    def __init__(self, converter):
        usdUtils.NodeManager.__init__(self)
        self.converter = converter


    def overrideGetName(self, strNodeIdx):
        # TODO: make sure there is no duplicate names
        if strNodeIdx is None:
            return ''
        nodeIdx = int(strNodeIdx)
        gltfNode = self.converter.gltf['nodes'][nodeIdx]
        return getName(gltfNode, 'node_', nodeIdx)


    def overrideGetChildren(self, strNodeIdx):
        children = []
        if strNodeIdx is None:
            for i in range(len(self.converter.gltf['nodes'])):
                if self.overrideGetParent(str(i)) is None:
                    children.append(str(i))
            return children
        gltfNode = self.converter.gltf['nodes'][int(strNodeIdx)]
        if 'children' in gltfNode:
            for child in gltfNode['children']:
                children.append(str(child))
        return children


    def overrideGetLocalTransformGfMatrix4d(self, strNodeIdx):
        if strNodeIdx is None:
            return Gf.Matrix4d(1)
        gltfNode = self.converter.gltf['nodes'][int(strNodeIdx)]
        return getMatrixTransform(gltfNode)


    def overrideGetWorldTransformGfMatrix4d(self, strNodeIdx):
        if strNodeIdx is None:
            return Gf.Matrix4d(1)
        return self.converter.getWorldTransform(int(strNodeIdx))


    def overrideGetParent(self, node):
        parentIdx = self.converter.getParent(int(node))
        if parentIdx == -1:
            return None
        return str(parentIdx)



class Accessor:
    def __init__(self, gltfData, accessorIdx):
        gltfAccessor = gltfData.gltf['accessors'][accessorIdx]
        accessorByteOffset = getInt(gltfAccessor, 'byteOffset')
        self.componentType = int(gltfAccessor['componentType'])
        fmt = glTFComponentType(self.componentType).unpackFormat()

        bufferViewIdx = gltfAccessor['bufferView']
        bufferView = gltfData.gltf['bufferViews'][bufferViewIdx]
        byteLength = bufferView['byteLength']
        byteOffset = getInt(bufferView, 'byteOffset')
        bufferIdx = bufferView['buffer']

        fileContent = gltfData.buffers[bufferIdx]
        offset = accessorByteOffset + byteOffset

        self.count = gltfAccessor['count']
        self.type = gltfAccessor['type']
        self.components = numOfComponents(self.type)

        self.stride = getInt(bufferView, 'byteStride')
        if self.stride != 0 and self.stride != glTFComponentType(self.componentType).size() * self.components:
            elementsSize = glTFComponentType(self.componentType).size() * self.components
            data = b''  # bytes, not str: Py2 relic crashed all strided/interleaved buffers
            for i in range(self.count):
                start = offset + i * self.stride
                data += fileContent[start : start + elementsSize]
            self.data = numpy.frombuffer(data, fmt, self.count * self.components)
        else:
            self.data = numpy.frombuffer(fileContent, fmt, self.count * self.components, offset)



class glTFConverter:
    def __init__(self, gltfPath, usdPath, legacyModifier, copyTextures, verbose):
        self.usdStage = None
        self.buffers = []
        self.gltf = None
        self.usdGeoms = {}
        self.usdMaterials = []
        self.usdSkelAnims = []
        self.nodeNames = {} # to avoid duplicate node names
        self.copyTextures = copyTextures
        self.verbose = verbose
        self.legacyModifier = legacyModifier # for iOS 12 compatibility
        self.skeletonByNode = {} # collect skinned mesh to construct later
        self._worldTransforms = {} # use self.getWorldTransform(nodeIdx)
        self._parents = {} # use self.getParent(nodeIdx)
        self._loadFailed = False
        # Morph targets / blendshapes (UsdSkel.BlendShape):
        #   morphState[strNodeIdx] = { 'names': [shape names in authored order],
        #                              'skinSkeleton': usdUtils.Skeleton or None,
        #                              'synthSkelPath': Sdf path string or None }
        self.morphState = {}
        # Set while processing a morph-only mesh so processPrimitive can bind
        # the synthetic skeleton (mirrors the codebase's context-passing style).
        self._currentMorphSkelPath = None

        filenameFull = gltfPath.split('/')[-1]
        self.srcFolder = gltfPath[:len(gltfPath)-len(filenameFull)]

        filenameFull = usdPath.split('/')[-1]
        self.dstFolder = usdPath[:len(usdPath)-len(filenameFull)]

        if self.legacyModifier is not None and self.legacyModifier.getMetersPerUnit() == 0:
            self.legacyModifier.setMetersPerUnit(1)
        self.asset = usdUtils.Asset(usdPath, legacyModifier)

        try:
            self.load(gltfPath)
        except:
            usdUtils.printError("can't load the input file.")
            self._loadFailed = True
            return
        if not self.checkGLTFVersion():
            return
        self.readAllBuffers()

        self.nodeManager = glTFNodeManager(self)
        self.skinning = usdUtils.Skinning(self.nodeManager)


    def load(self, gltfPath):
        fileAndExt = os.path.splitext(gltfPath)
        if len(fileAndExt) == 2 and fileAndExt[1].lower() == '.glb':
            with open(gltfPath, "rb") as file:
                (magic, version, length) = loadChunk(file, '<3i')
                (jsonLen, jsonType) = loadChunk(file, '<2i')
                self.gltf = json.loads(file.read(jsonLen))
                (bufferLen, bufferType) = loadChunk(file, '<2i')
                self.buffers.append(file.read())
        else:
            with open(gltfPath) as file:
                self.gltf = json.load(file)


    def checkGLTFVersion(self):
        if 'asset' in self.gltf and 'version' in self.gltf['asset']:
            version = self.gltf['asset']['version']
            if float(version) < 2.0 or float(version) >= 3.0:
                usdUtils.printError('glTF 2.x is supported only. Version of glTF of input file is ' + version)
                self._loadFailed = True
        else:
            usdUtils.printError("can't detect the version of glTF.")
            self._loadFailed = True
        return not self._loadFailed


    def _fillWorldTransforms(self, children, parentWorldTransform):
        for nodeIdx in children:
            gltfNode = self.gltf['nodes'][nodeIdx]
            worldTransform =  getMatrixTransform(gltfNode) * parentWorldTransform
            self._worldTransforms[str(nodeIdx)] = worldTransform
            if 'children' in gltfNode:
                self._fillWorldTransforms(gltfNode['children'], worldTransform)


    def getWorldTransform(self, nodeIdx):
        if nodeIdx == -1:
            return Gf.Matrix4d(1)
        if not self._worldTransforms:
            self._fillWorldTransforms(self.gltf['scenes'][0]['nodes'], Gf.Matrix4d(1))
        return self._worldTransforms[str(nodeIdx)]


    def _fillParents(self, children, parentId):
        for nodeIdx in children:
            gltfNode = self.gltf['nodes'][nodeIdx]
            self._parents[str(nodeIdx)] = parentId
            if 'children' in gltfNode:
                self._fillParents(gltfNode['children'], nodeIdx)


    def getParent(self, nodeIdx):
        if nodeIdx == -1:
            return -1
        if not self._parents:
            self._fillParents(self.gltf['scenes'][0]['nodes'], -1)
        return self._parents[str(nodeIdx)]


    def saveTexture(self, content, mimeType, textureIdx):
        if not os.path.isdir(self.dstFolder + 'textures'):
            os.mkdir(self.dstFolder + 'textures')

        ext = '.png'
        if mimeType == 'image/jpeg':
            ext = '.jpg'
        filename = 'textures/texgen_' + str(textureIdx) + ext

        if hasattr(content, '_array'):
            content = content._array.tostring()
        
        newfile = open(self.dstFolder + filename, 'wb')
        newfile.write(content)
        return filename


    def saveTextureWithImage(self, image, textureIdx):
        bufferViewIdx = image['bufferView']
        bufferView = self.gltf['bufferViews'][bufferViewIdx]
        byteLength = bufferView['byteLength']
        byteOffset = getInt(bufferView, 'byteOffset')
        bufferIdx = bufferView['buffer']

        buffer = self.buffers[bufferIdx]
        content = numpy.frombuffer(buffer, numpy.uint8, byteLength, byteOffset)
        return self.saveTexture(content, image['mimeType'], textureIdx)


    def processTexture(self, dict, type, inputName, channels, material, scale = None):
        if type not in dict:
            return False

        gltfMaterialMap = dict[type]
        textureIdx = gltfMaterialMap['index']
        texCoordSet = gltfMaterialMap['texCoord'] if 'texCoord' in gltfMaterialMap else 0
        gltfTexture = self.gltf['textures'][textureIdx]
        sourceIdx = gltfTexture['source']
        image = self.gltf['images'][sourceIdx]

        srcTextureFilename = '' # source texture filename on drive
        textureFilename = '' # valid for USD
        if 'uri' in image:
            uri = image['uri']
            if len(uri) > 5 and uri[:5] == 'data:':
                # embedded texture
                for offset in range(5, len(uri) - 6):
                    if uri[offset:(offset+6)] == 'base64':
                        mimeType = uri[5:(offset-1)] if offset > 6 else ''
                        content = base64.b64decode(uri[(offset + 6):])
                        textureFilename = self.saveTexture(content, mimeType, textureIdx)
                        srcTextureFilename = self.dstFolder + textureFilename
                        break
            else:
                srcTextureFilename = uri
                textureFilename = usdUtils.makeValidPath(srcTextureFilename)
                filenameAndExt = os.path.splitext(textureFilename)
                ext = filenameAndExt[1].lower()
                if '.jpeg' == ext:
                    textureFilename = filenameAndExt[0] + '.jpg'
                    usdUtils.copy(self.srcFolder + srcTextureFilename, self.dstFolder + textureFilename, self.verbose)
                elif self.srcFolder != self.dstFolder:
                    if self.copyTextures or srcTextureFilename != textureFilename:
                        usdUtils.copy(self.srcFolder + srcTextureFilename, self.dstFolder + textureFilename, self.verbose)
                    else:
                        textureFilename = self.srcFolder + textureFilename
                srcTextureFilename = self.srcFolder + srcTextureFilename

        elif 'mimeType' in image and 'bufferView' in image:
            textureFilename = self.saveTextureWithImage(image, textureIdx)
            srcTextureFilename = self.dstFolder + textureFilename

        if textureFilename == '':
            return False

        if self.legacyModifier is not None and (channels == 'g' or channels == 'b' or channels == 'r'):
            newTextureFilename = self.legacyModifier.makeOneChannelTexture(srcTextureFilename, self.dstFolder, channels, self.verbose)
            if newTextureFilename:
                textureFilename = newTextureFilename
                channels = 'r'

        wrapS = 'repeat' # default for glTF
        wrapT = 'repeat' # default for glTF

        # Wrapping mode
        if 'sampler' in gltfTexture:
            samplerIdx = gltfTexture['sampler']
            gltfSampler = self.gltf['samplers'][samplerIdx]
            if 'wrapS' in gltfSampler:
                wrapS = glTFWrappingMode(gltfSampler['wrapS']).usdMode()
            if 'wrapT' in gltfSampler:
                wrapT = glTFWrappingMode(gltfSampler['wrapT']).usdMode()

        primvarName = 'st' if texCoordSet == 0 else 'st' + str(texCoordSet)
        material.inputs[inputName] = usdUtils.Map(channels, textureFilename, None, primvarName, wrapS, wrapT, scale)
        return True


    def readAllBuffers(self):
        for buffer in self.gltf['buffers']:
            if 'uri' in buffer:
                uri = buffer['uri']
                if len(uri) > 5 and uri[:5] == 'data:':
                    for offset in range(5, len(uri) - 6):
                        if uri[offset:(offset+6)] == 'base64':
                            fileContent = base64.b64decode(uri[(offset + 6):])
                            self.buffers.append(fileContent)
                            break
                else:
                    bufferFileName = self.srcFolder + uri
                    with open(bufferFileName, mode='rb') as file:
                        fileContent = file.read()
                    self.buffers.append(fileContent)


    def textureHasAlpha(self, filename):
        filenameAndExt = os.path.splitext(filename)
        ext = filenameAndExt[1].lower()
        if '.jpg' == ext:
            return False
        return True


    def createMaterials(self):
        for gltfMaterial in self.gltf['materials'] if 'materials' in self.gltf else []:
            matName = getName(gltfMaterial, 'material_', len(self.usdMaterials))
            material = usdUtils.Material(matName)

            isBlend = False
            if 'alphaMode' in gltfMaterial and gltfMaterial['alphaMode'] == 'BLEND':
                isBlend = True

            if 'alphaMode' in gltfMaterial and gltfMaterial['alphaMode'] == 'MASK':
                isBlend = True
                if 'alphaCutoff' in gltfMaterial:
                    material.opacityThreshold = float(gltfMaterial['alphaCutoff'])
                else:
                    material.opacityThreshold = 0.5

            pbr = None
            if 'pbrMetallicRoughness' in gltfMaterial:
                pbr = gltfMaterial['pbrMetallicRoughness']

                # diffuse color and opacity
                baseColorFactor = pbr['baseColorFactor'] if 'baseColorFactor' in pbr else [1, 1, 1, 1]
                baseColorScale = [baseColorFactor[0], baseColorFactor[1], baseColorFactor[2]]
                opacityScale = baseColorFactor[3]
                if self.processTexture(pbr, 'baseColorTexture', usdUtils.InputName.diffuseColor, 'rgb', material, baseColorScale):
                    if isBlend:
                        map = material.inputs[usdUtils.InputName.diffuseColor]
                        if self.textureHasAlpha(map.file):
                            self.processTexture(pbr, 'baseColorTexture', usdUtils.InputName.opacity, 'a', material, opacityScale)
                        else:
                            material.inputs[usdUtils.InputName.opacity] = baseColorFactor[3]
                else:
                    material.inputs[usdUtils.InputName.diffuseColor] = baseColorFactor
                    if isBlend:
                        material.inputs[usdUtils.InputName.opacity] = baseColorFactor[3]
                
                # metallic and roughness
                roughnessFactor = pbr['roughnessFactor'] if 'roughnessFactor' in pbr else 1.0
                metallicFactor = pbr['metallicFactor'] if 'metallicFactor' in pbr else 1.0
                if 'metallicRoughnessTexture' in pbr:
                    self.processTexture(pbr, 'metallicRoughnessTexture', usdUtils.InputName.roughness, 'g', material, roughnessFactor)
                    self.processTexture(pbr, 'metallicRoughnessTexture', usdUtils.InputName.metallic, 'b', material, metallicFactor)
                else:
                    material.inputs[usdUtils.InputName.roughness] = roughnessFactor
                    material.inputs[usdUtils.InputName.metallic] = metallicFactor

            elif 'extensions' in gltfMaterial and 'KHR_materials_pbrSpecularGlossiness' in gltfMaterial['extensions']:
                if self.verbose:
                    usdUtils.printWarning("specular/glossiness workflow is not fully supported.")
                pbrSG = gltfMaterial['extensions']['KHR_materials_pbrSpecularGlossiness']
                diffuseScale = None
                opacityScale = None
                if 'diffuseFactor' in pbrSG:
                    diffuseFactor = pbrSG['diffuseFactor']
                    diffuseScale = [diffuseFactor[0], diffuseFactor[1], diffuseFactor[2]]
                    opacityScale = diffuseFactor[3]
                if self.processTexture(pbrSG, 'diffuseTexture', usdUtils.InputName.diffuseColor, 'rgb', material, diffuseScale):
                    if isBlend:
                        map = material.inputs[usdUtils.InputName.diffuseColor]
                        if self.textureHasAlpha(map.file):
                            self.processTexture(pbrSG, 'diffuseTexture', usdUtils.InputName.opacity, 'a', material, opacityScale)
                        else:
                            material.inputs[usdUtils.InputName.opacity] = opacityScale
                else:
                    if diffuseScale:
                        material.inputs[usdUtils.InputName.diffuseColor] = diffuseScale
                    if isBlend and opacityScale:
                        material.inputs[usdUtils.InputName.opacity] = opacityScale

            self.processTexture(gltfMaterial, 'normalTexture', usdUtils.InputName.normal, 'rgb', material)
            self.processTexture(gltfMaterial, 'occlusionTexture', usdUtils.InputName.occlusion, 'r', material) #TODO: add occlusion scale

            emissiveFactor = gltfMaterial['emissiveFactor'] if 'emissiveFactor' in gltfMaterial else [0.0, 0.0, 0.0]
            if not self.processTexture(gltfMaterial, 'emissiveTexture', usdUtils.InputName.emissiveColor, 'rgb', material, emissiveFactor):
                if gltfMaterial != None and 'emissiveFactor' in gltfMaterial:
                    material.inputs[usdUtils.InputName.emissiveColor] = gltfMaterial['emissiveFactor']

            usdMaterial = material.makeUsdMaterial(self.asset)
            self.usdMaterials.append(usdMaterial)


    def prepareSkinning(self):
        if 'skins' not in self.gltf:
            return

        for skinIdx in range(len(self.gltf['skins'])):
            gltfSkin = self.gltf['skins'][skinIdx]

            root = str(gltfSkin['skeleton']) if 'skeleton' in gltfSkin else None
            skin = usdUtils.Skin(root)

            gltfJoints = gltfSkin['joints']
            for jointIdx in gltfJoints:
                joint = str(jointIdx)
                skin.joints.append(joint)

            # get bind matrices
            if 'inverseBindMatrices' in gltfSkin:
                bindMatAcc = Accessor(self, gltfSkin['inverseBindMatrices'])
                m = bindMatAcc.data
                i = 0
                for jointIdx in gltfJoints:
                    mat = Gf.Matrix4d(
                        float(m[i + 0]), float(m[i + 1]), float(m[i + 2]), float(m[i + 3]),
                        float(m[i + 4]), float(m[i + 5]), float(m[i + 6]), float(m[i + 7]),
                        float(m[i + 8]), float(m[i + 9]), float(m[i +10]), float(m[i +11]),
                        float(m[i +12]), float(m[i +13]), float(m[i +14]), float(m[i +15]))
                    skin.bindMatrices[str(jointIdx)] = mat.GetInverse()
                    i += bindMatAcc.components
            else:
                # default identity matrices by spec, which implies that inverse-bind matrices were pre-applied
                for jointIdx in gltfJoints:
                    skin.bindMatrices[str(jointIdx)] = Gf.Matrix4d(1)

            self.skinning.skins.append(skin)
        self.skinning.createSkeletonsFromSkins()
        if self.verbose:
            print("  Found skeletons:", len(self.skinning.skeletons), "with", len(self.skinning.skins), "skin(s)")
        for skeleton in self.skinning.skeletons:
            if skeleton.getRoot() is None:
                skeleton.makeUsdSkeleton(self.usdStage, self.asset.getGeomPath() + '/RootNodeSkel', self.nodeManager)


    def findSkeletonForAnimation(self, gltfAnim):
        for gltfChannel in gltfAnim['channels']:
            gltfTarget = gltfChannel['target']
            if 'node' not in gltfTarget:
                continue
            nodeIdx = gltfTarget['node']
            skeleton = self.skinning.findSkeletonByJoint(str(nodeIdx))
            if skeleton is not None:
                return skeleton
        return None


    def prepareAnimations(self):
        if 'animations' not in self.gltf:
            return
        # find good FPS based on key time data
        minTimeInterval = 1.0 / 24 # default for USD
        epsilon = 0.01
        for gltfAnim in self.gltf['animations']:
            for gltfChannel in gltfAnim['channels']:
                samplerIdx = gltfChannel['sampler']
                gltfSampler = gltfAnim['samplers'][samplerIdx]
                keyTimesAcc = Accessor(self, gltfSampler['input'])
                for el in range(keyTimesAcc.count-1):
                    timeInterval = keyTimesAcc.data[el+1] - keyTimesAcc.data[el]
                    if minTimeInterval > timeInterval and timeInterval > epsilon:
                        minTimeInterval = timeInterval
        self.asset.setFPS(int(1.0 / minTimeInterval))


    def getInterpolatedValues(self, interpolation, keyTimesAcc, keyValuesAcc, getValueFromData, timeSet=None):
        values = {}
        data = keyValuesAcc.data
        if interpolation == 'CUBICSPLINE':
            for el in range(keyTimesAcc.count - 1):
                t0 = self.asset.toTimeCode(keyTimesAcc.data[el], True)
                t1 = self.asset.toTimeCode(keyTimesAcc.data[el + 1], True)

                smallTimeRange = 0.00001
                timeRange = t1 - t0
                if timeRange < smallTimeRange: timeRange = smallTimeRange
                timeSteps = int(timeRange)
                if timeSteps == 0: timeSteps = 1

                # math is described in glTF specification
                offset = el * keyValuesAcc.components * 3 + keyValuesAcc.components
                p0 = getValueFromData(data, offset)
                offset = el * keyValuesAcc.components * 3 + keyValuesAcc.components * 2
                m0 = getValueFromData(data, offset) * timeRange
                offset = (el + 1) * keyValuesAcc.components * 3
                m1 = getValueFromData(data, offset) * timeRange
                offset = (el + 1) * keyValuesAcc.components * 3 + keyValuesAcc.components
                p1 = getValueFromData(data, offset)

                for timeStep in range(timeSteps):
                    t = float(timeStep) / timeSteps
                    t2 = t * t
                    t3 = t2 * t
                    p = (2*t3 - 3*t2 + 1) * p0 + (t3 - 2*t2 + t) * m0 + (-2*t3 + 3*t2) * p1 + (t3 - t2) * m1
                    if type(p) is Gf.Quatf:
                        p = p.GetNormalized()
                    values[t0 + timeStep] = p
                    if timeSet is not None:
                        timeSet.add(t0 + timeStep)

            el = keyTimesAcc.count - 1
            time = self.asset.toTimeCode(keyTimesAcc.data[el], True)
            offset = el * keyValuesAcc.components * 3 + keyValuesAcc.components
            values[time] = getValueFromData(data, offset)
            if timeSet is not None:
                timeSet.add(time)
        else:
            if interpolation == 'STEP':
                for el in range(1, keyTimesAcc.count):
                    time = self.asset.toTimeCode(keyTimesAcc.data[el], True) - 1
                    offset = (el - 1) * keyValuesAcc.components
                    values[time] = getValueFromData(data, offset)
                    if timeSet is not None:
                        timeSet.add(time)
            for el in range(keyTimesAcc.count):
                time = self.asset.toTimeCode(keyTimesAcc.data[el], True)
                offset = el * keyValuesAcc.components
                values[time] = getValueFromData(data, offset)
                if timeSet is not None:
                    timeSet.add(time)

        return values


    def _authorBlendShapes(self, nodeIdx, gltfPrimitive, usdMesh, usdSkelBinding, skin, skeleton, path):
        # glTF morph targets -> UsdSkel.BlendShape prims (children of the mesh),
        # following the structure Blender's exporter produces (see
        # docs/morph-implementation.md). Weight animation is authored later by
        # processMorphWeightAnimations().
        targets = gltfPrimitive.get('targets')
        if not targets or not isinstance(usdMesh, UsdGeom.Mesh):
            return

        gltfNode = self.gltf['nodes'][nodeIdx]
        meshIdx = gltfNode['mesh']
        targetNames = self.gltf['meshes'][meshIdx].get('extras', {}).get('targetNames')

        binding = usdSkelBinding
        if binding is None:
            binding = UsdSkel.BindingAPI.Apply(usdMesh.GetPrim())
        if self._currentMorphSkelPath is not None:
            binding.CreateSkeletonRel().AddTarget(self._currentMorphSkelPath)

        strNodeIdx = str(nodeIdx)
        state = self.morphState.setdefault(
            strNodeIdx, {'names': [], 'skinSkeleton': None, 'synthSkelPath': None})

        # glTF morph targets are defined per-MESH: every primitive of the mesh
        # shares the same target list and the same weights stream. So shape
        # names are computed deterministically per target index — a second
        # primitive re-authors its own BlendShape prims under its own path but
        # binds the SAME names, letting one SkelAnimation drive all primitives.
        names = []
        shapePaths = []
        for i in range(len(targets)):
            target = targets[i]
            if 'POSITION' not in target:
                usdUtils.printWarning('morph target %d has no POSITION offsets; dropped.' % i)
                continue
            accIdx = target['POSITION']
            if 'sparse' in self.gltf['accessors'][accIdx]:
                usdUtils.printWarning(
                    'sparse accessor in morph target %d is not supported; target dropped.' % i)
                continue

            name = None
            if targetNames is not None and i < len(targetNames):
                name = makeValidPrimName(str(targetNames[i]))
            if not name:
                name = 'shape_' + str(i)
            if name in names:  # sanitized duplicates within this target list
                name = name + '_' + str(i)

            acc = Accessor(self, accIdx)
            data = acc.data
            offsets = Vt.Vec3fArray(acc.count)
            for el in range(acc.count):
                offsets[el] = Gf.Vec3f(float(data[el * 3]),
                                       float(data[el * 3 + 1]),
                                       float(data[el * 3 + 2]))

            usdBlendShape = UsdSkel.BlendShape.Define(self.usdStage, path + '/' + name)
            usdBlendShape.CreateOffsetsAttr(offsets)
            usdBlendShape.CreatePointIndicesAttr(Vt.IntArray(list(range(acc.count))))

            if 'NORMAL' in target and 'sparse' not in self.gltf['accessors'][target['NORMAL']]:
                nAcc = Accessor(self, target['NORMAL'])
                nData = nAcc.data
                normalOffsets = Vt.Vec3fArray(nAcc.count)
                for el in range(nAcc.count):
                    normalOffsets[el] = Gf.Vec3f(float(nData[el * 3]),
                                                 float(nData[el * 3 + 1]),
                                                 float(nData[el * 3 + 2]))
                usdBlendShape.CreateNormalOffsetsAttr(normalOffsets)

            names.append(name)
            shapePaths.append(usdBlendShape.GetPath())

        if not names:
            return

        binding.CreateBlendShapesAttr().Set(names)
        rel = binding.CreateBlendShapeTargetsRel()
        for shapePath in shapePaths:
            rel.AddTarget(shapePath)

        # Mesh-level name list: identical for every primitive of this mesh.
        if not state['names']:
            state['names'] = names
        if skin is not None and skin.skeleton is not None:
            state['skinSkeleton'] = skin.skeleton
        elif skeleton is not None:
            state['skinSkeleton'] = skeleton
        if self._currentMorphSkelPath is not None:
            state['synthSkelPath'] = self._currentMorphSkelPath


    def _skelAnimForMorphState(self, strNodeIdx, state):
        # Find (or create) the SkelAnimation that should carry blendShapeWeights
        # for this mesh node.
        skinSkel = state['skinSkeleton']
        if skinSkel is not None and skinSkel.usdSkelAnim is not None:
            return skinSkel.usdSkelAnim
        if state.get('usdSkelAnim') is not None:
            return state['usdSkelAnim']

        anim = None
        if state['synthSkelPath'] is not None:
            # Morph-only mesh: animation lives under the synthesized skeleton.
            anim = UsdSkel.Animation.Define(self.usdStage, state['synthSkelPath'] + '/Anim')
            skelPrim = self.usdStage.GetPrimAtPath(state['synthSkelPath'])
            UsdSkel.BindingAPI.Apply(skelPrim).CreateAnimationSourceRel().AddTarget(anim.GetPath())
        elif skinSkel is not None and skinSkel.usdSkeleton is not None:
            # Skeleton exists but carries no joint animation of its own.
            animPath = self.asset.getAnimationsPath() + '/morphAnim_' + strNodeIdx
            anim = UsdSkel.Animation.Define(self.usdStage, animPath)
            UsdSkel.BindingAPI.Apply(skinSkel.usdSkeleton.GetPrim()) \
                .CreateAnimationSourceRel().AddTarget(anim.GetPath())
        state['usdSkelAnim'] = anim
        return anim


    def processMorphWeightAnimations(self):
        # glTF animation channels with target.path == 'weights' -> time-sampled
        # blendShapeWeights on the SkelAnimation bound to the mesh's skeleton.
        for gltfAnim in self.gltf['animations'] if 'animations' in self.gltf else []:
            for gltfChannel in gltfAnim['channels']:
                gltfTarget = gltfChannel['target']
                if gltfTarget.get('path') != 'weights' or 'node' not in gltfTarget:
                    continue
                strNodeIdx = str(gltfTarget['node'])
                state = self.morphState.get(strNodeIdx)
                if state is None or not state['names']:
                    continue  # targets were dropped (e.g. sparse) and warned about

                n = len(state['names'])
                gltfSampler = gltfAnim['samplers'][gltfChannel['sampler']]
                interpolation = gltfSampler.get('interpolation', 'LINEAR')
                keyTimesAcc = Accessor(self, gltfSampler['input'])
                keyValuesAcc = Accessor(self, gltfSampler['output'])
                tdata = keyTimesAcc.data
                vdata = keyValuesAcc.data

                samples = {}  # timeCode -> [weights] * n
                if interpolation == 'CUBICSPLINE':
                    # per key: [inTangents*n, values*n, outTangents*n]; bake
                    # per-frame with the same hermite math the joint path uses
                    for el in range(keyTimesAcc.count - 1):
                        t0 = self.asset.toTimeCode(tdata[el], True)
                        t1 = self.asset.toTimeCode(tdata[el + 1], True)
                        timeRange = max(t1 - t0, 0.00001)
                        steps = max(int(timeRange), 1)
                        base0 = el * n * 3
                        base1 = (el + 1) * n * 3
                        for step in range(steps):
                            t = float(step) / steps
                            t2 = t * t
                            t3 = t2 * t
                            weights = []
                            for i in range(n):
                                p0 = float(vdata[base0 + n + i])
                                m0 = float(vdata[base0 + 2 * n + i]) * timeRange
                                m1 = float(vdata[base1 + i]) * timeRange
                                p1 = float(vdata[base1 + n + i])
                                weights.append(
                                    (2*t3 - 3*t2 + 1) * p0 + (t3 - 2*t2 + t) * m0
                                    + (-2*t3 + 3*t2) * p1 + (t3 - t2) * m1)
                            samples[t0 + step] = weights
                    el = keyTimesAcc.count - 1
                    base = el * n * 3
                    samples[self.asset.toTimeCode(tdata[el], True)] = [
                        float(vdata[base + n + i]) for i in range(n)]
                else:
                    if interpolation == 'STEP':
                        for el in range(1, keyTimesAcc.count):
                            time = self.asset.toTimeCode(tdata[el], True) - 1
                            samples[time] = [float(vdata[(el - 1) * n + i]) for i in range(n)]
                    # LINEAR keys author exactly: USD lerps between time samples
                    for el in range(keyTimesAcc.count):
                        time = self.asset.toTimeCode(tdata[el], True)
                        samples[time] = [float(vdata[el * n + i]) for i in range(n)]

                usdSkelAnim = self._skelAnimForMorphState(strNodeIdx, state)
                if usdSkelAnim is None:
                    usdUtils.printWarning(
                        'no skeleton to carry blendshape weights for node ' + strNodeIdx)
                    continue
                usdSkelAnim.CreateBlendShapesAttr().Set(state['names'])
                weightsAttr = usdSkelAnim.CreateBlendShapeWeightsAttr()
                for time in sorted(samples):
                    weightsAttr.Set(Vt.FloatArray(samples[time]), Usd.TimeCode(float(time)))


    def processSkeletonAnimation(self):
        for gltfAnim in self.gltf['animations'] if 'animations' in self.gltf else []:

            skeleton = self.findSkeletonForAnimation(gltfAnim)
            if skeleton is None:
                continue

            name = getName(gltfAnim, 'skelAnim_', len(self.usdSkelAnims))

            # animJoints is a matrix of all animated values with time keys
            # animJoints is a dictionary with joint ids as keys
            # each element of animJoints has a three elements list: [0] -- translations, [1] -- rotations, [2] -- scales
            # each of it has a dictionary with time keys {0: value, 1: next value... }
            animJoints = {}

            translationTimeSet = set()
            rotationTimeSet = set()
            scaleTimeSet = set()

            # Fill animJoints
            for gltfChannel in gltfAnim['channels']:
                gltfTarget = gltfChannel['target']
                strNodeIdx = str(gltfTarget['node'])

                if skeleton.getJointIndex(strNodeIdx) == -1:
                    if self.verbose:
                        usdUtils.printWarning("Skeletal animation contains node animation")
                    continue

                targetPath = gltfTarget['path']

                samplerIdx = gltfChannel['sampler']
                gltfSampler = gltfAnim['samplers'][samplerIdx]
                interpolation = gltfSampler['interpolation'] if 'interpolation' in gltfSampler else 'LINEAR'

                keyTimesAcc = Accessor(self, gltfSampler['input'])
                keyValuesAcc = Accessor(self, gltfSampler['output'])

                if strNodeIdx not in animJoints:
                    animJoints[strNodeIdx] = [None] * 3

                pathIdx = -1
                timeSet = None
                if targetPath == 'translation':
                    pathIdx = 0
                    timeSet = translationTimeSet
                elif targetPath == 'rotation':
                    pathIdx = 1
                    timeSet = rotationTimeSet
                elif targetPath == 'scale':
                    pathIdx = 2
                    timeSet = scaleTimeSet
                else:
                    if self.verbose:
                        usdUtils.printWarning("Skeletal animation: unsupported target path: " + targetPath)
                    continue

                getValueFromData = getGfQuatfFromData if targetPath == 'rotation' else getGfVec3fFromData
                values = self.getInterpolatedValues(interpolation, keyTimesAcc, keyValuesAcc, getValueFromData, timeSet)
                animJoints[strNodeIdx][pathIdx] = values

            if len(animJoints) == 0:
                continue

            animationPath = self.asset.getAnimationsPath() + '/' + name
            usdSkelAnim = UsdSkel.Animation.Define(self.usdStage, animationPath)

            jointPaths = []
            for joint in skeleton.joints:
                if joint in animJoints:
                    jointPaths.append(skeleton.jointPaths[joint])

            usdSkelAnim.CreateJointsAttr().Set(jointPaths)

            gltfNodes = self.gltf['nodes']

            # translations attribute
            times = sorted(translationTimeSet)
            attr = usdSkelAnim.CreateTranslationsAttr()
            for time in times:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        animJoint = animJoints[joint]
                        if animJoint[0]:
                            values.append(getInterpolatedValue(animJoint[0], time))
                        else:
                            values.append(getTransformTranslation(gltfNodes[int(joint)]))
                if len(values):
                    # times may be numpy.float32 (from accessor data); modern USD's
                    # TimeCode binding only accepts a Python double.
                    attr.Set(values, Usd.TimeCode(float(time)))
            if len(times) == 0: # add default values if no keys
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        values.append(Gf.Vec3f(0, 0, 0))
                attr.Set(values)

            # rotations attribute
            times = sorted(rotationTimeSet)
            attr = usdSkelAnim.CreateRotationsAttr()
            for time in times:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        animJoint = animJoints[joint]
                        if animJoint[1]:
                            values.append(getInterpolatedValue(animJoint[1], time, True))
                        else:
                            values.append(getTransformRotation(gltfNodes[int(joint)]))
                if len(values):
                    # times may be numpy.float32 (from accessor data); modern USD's
                    # TimeCode binding only accepts a Python double.
                    attr.Set(values, Usd.TimeCode(float(time)))
            if len(times) == 0:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        values.append(Gf.Quatf(1, Gf.Vec3f(0, 0, 0)))
                attr.Set(values)

            # scales attribute
            times = sorted(scaleTimeSet)
            attr = usdSkelAnim.CreateScalesAttr()
            for time in times:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        animJoint = animJoints[joint]
                        if animJoint[2]:
                            values.append(getInterpolatedValue(animJoint[2], time))
                        else:
                            values.append(getTransformScale(gltfNodes[int(joint)]))
                if len(values):
                    # times may be numpy.float32 (from accessor data); modern USD's
                    # TimeCode binding only accepts a Python double.
                    attr.Set(values, Usd.TimeCode(float(time)))
            if len(times) == 0:
                values = []
                for joint in skeleton.joints:
                    if joint in animJoints:
                        values.append(Gf.Vec3f(1, 1, 1))
                attr.Set(values)

            skeleton.setSkeletalAnimation(usdSkelAnim)
            self.usdSkelAnims.append(usdSkelAnim)


    def processPrimitive(self, nodeIdx, gltfPrimitive, path, skinIdx, skeleton):
        mode = gltfPrimitive['mode'] if 'mode' in gltfPrimitive else gltfPrimitiveMode.TRIANGLES

        usdMesh = None
        if mode == gltfPrimitiveMode.POINTS:
            usdMesh = UsdGeom.Points.Define(self.usdStage, path)
        elif mode == gltfPrimitiveMode.LINES:
            usdUtils.printWarning('LINES as primitive.mode is not supported.')
            return UsdGeom.Xform.Define(self.usdStage, path)
        elif mode == gltfPrimitiveMode.LINE_LOOP:
            usdUtils.printWarning('LINE_LOOP as primitive.mode is not supported.')
            return UsdGeom.Xform.Define(self.usdStage, path)
        elif mode == gltfPrimitiveMode.LINE_STRIP:
            usdUtils.printWarning('LINE_STRIP as primitive.mode is not supported.')
            return UsdGeom.Xform.Define(self.usdStage, path)

        if usdMesh is None:
            usdMesh = UsdGeom.Mesh.Define(self.usdStage, path)

        usdSkelBinding = None
        skin = None
        if skinIdx != -1:
            skin = self.skinning.skins[skinIdx]
            if skin.skeleton is not None:
                usdSkelBinding = UsdSkel.BindingAPI.Apply(usdMesh.GetPrim())
                differenceTransform = Gf.Matrix4d(1)
                usdSkelBinding.CreateGeomBindTransformAttr(differenceTransform)
                if skin.skeleton.usdSkeleton is not None:
                    usdSkelBinding.CreateSkeletonRel().AddTarget(skin.skeleton.usdSkeleton.GetPath())
                    if self.legacyModifier is not None:
                        self.legacyModifier.addSkelAnimToMesh(usdMesh, skin.skeleton)
        elif skeleton is not None:
            # geomBindTransform must live in the same space as the skeleton's
            # bindTransforms: the skeleton root's PARENT space (skin IBMs cancel
            # every ancestor transform, including armature scale). A raw world
            # matrix double-applies those ancestors — three.js/Blender armatures
            # carry scale=100, which rendered rigid meshes 100x too big and made
            # Quick Look show a blank scene (you were inside the model).
            meshNodeWorldMatrix = self.getWorldTransform(nodeIdx)
            rootParentIdx = self.getParent(int(skeleton.getRoot()))
            skelSpaceMatrix = self.getWorldTransform(rootParentIdx)
            relativeMatrix = meshNodeWorldMatrix * skelSpaceMatrix.GetInverse()
            skeleton.bindRigidDeformation(str(nodeIdx), usdMesh, relativeMatrix)
            if self.legacyModifier is not None:
                self.legacyModifier.addSkelAnimToMesh(usdMesh, skeleton)

        attributes = gltfPrimitive['attributes']

        count = 0 # for geometry without indices
        for key in attributes:
            accessor = Accessor(self, attributes[key])

            if key == 'POSITION':
                points = accessor.data if _HAS_NUMPY else _pxrVec3fArrayFromAccessor(accessor)
                usdMesh.CreatePointsAttr(points)
                count = accessor.count
            elif key == 'NORMAL':
                normals = accessor.data if _HAS_NUMPY else _pxrVec3fArrayFromAccessor(accessor)
                usdMesh.CreateNormalsAttr(normals)
                usdMesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
            elif key == 'TANGENT':
                pass
            elif key[0:8] == 'TEXCOORD':
                if accessor.componentType != glTFComponentType.FLOAT:
                    if self.verbose:
                        print('Warnig: component type', accessor.componentType, 'is not supported for texture coordinates')
                    break
                # Y-component of texture coordinates should be flipped
                newData = []
                for el in range(accessor.count):
                    newData.append((
                        float(accessor.data[el * accessor.components]),
                        float(1.0 - accessor.data[el * accessor.components + 1])))

                texCoordSet = key[9:]
                primvarName = 'st' if texCoordSet == '0' else 'st' + texCoordSet
                uvs = UsdGeom.PrimvarsAPI(usdMesh).CreatePrimvar(primvarName, Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
                uvs.Set(newData)
            elif key == 'COLOR_0':
                data = accessor.data
                if accessor.type == 'VEC4':
                    # displayColor for USD should have Color3Array type
                    newData = []
                    for el in range(accessor.count):
                        newData.append((
                            float(data[el * accessor.components]),
                            float(data[el * accessor.components + 1]),
                            float(data[el * accessor.components + 2])))
                    data = newData
                usdMesh.CreateDisplayColorPrimvar(UsdGeom.Tokens.vertex).Set(data)
            elif key =='JOINTS_0':
                if usdSkelBinding != None:
                    newData = [0] * accessor.count * accessor.components
                    for i in range(accessor.count * accessor.components):
                        newData[i] = skin.remapIndex(accessor.data[i])
                    usdSkelBinding.CreateJointIndicesPrimvar(False, accessor.components).Set(newData)
            elif key =='WEIGHTS_0':
                if usdSkelBinding != None:
                    # Normalize weights
                    newData = Vt.FloatArray(list(map(float, accessor.data)))
                    UsdSkel.NormalizeWeights(newData, accessor.components)
                    usdSkelBinding.CreateJointWeightsPrimvar(False, accessor.components).Set(newData)
            else:
                usdUtils.printWarning("Unsupported primitive attribute: " + key)

        if (mode == gltfPrimitiveMode.TRIANGLES or 
            mode == gltfPrimitiveMode.TRIANGLE_STRIP or 
            mode == gltfPrimitiveMode.TRIANGLE_FAN):
            if 'indices' in gltfPrimitive:
                accessor = Accessor(self, gltfPrimitive['indices'])
                count = accessor.count
                indices = accessor.data
                if mode == gltfPrimitiveMode.TRIANGLE_STRIP:
                    indices = indicesWithTriangleStrip(accessor.data)
                    count = len(indices)
                elif mode == gltfPrimitiveMode.TRIANGLE_FAN:
                    indices = indicesWithTriangleFan(accessor.data)
                    count = len(indices)
                usdMesh.CreateFaceVertexIndicesAttr(_pxrIntArrayFromData(indices))
            elif count > 0:
                if mode == gltfPrimitiveMode.TRIANGLES:
                    count = int(count / 3) * 3 # should be divisible by 3
                indices = [0] * count
                for ind in range(count):
                    indices[ind] = ind 
                if mode == gltfPrimitiveMode.TRIANGLE_STRIP:
                    indices = indicesWithTriangleStrip(indices)
                    count = len(indices)
                elif mode == gltfPrimitiveMode.TRIANGLE_FAN:
                    indices = indicesWithTriangleFan(indices)
                    count = len(indices)
                usdMesh.CreateFaceVertexIndicesAttr(_pxrIntArrayFromData(indices))

            numFaceVertexCounts = count // 3
            faceVertexCounts = [3] * numFaceVertexCounts
            usdMesh.CreateFaceVertexCountsAttr(faceVertexCounts) # per-face vertex indices

            usdMesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)

        self._authorBlendShapes(nodeIdx, gltfPrimitive, usdMesh, usdSkelBinding, skin, skeleton, path)

        # bind material to mesh
        if 'material' in gltfPrimitive:
            materialIdx = gltfPrimitive['material']
            UsdShade.MaterialBindingAPI.Apply(usdMesh.GetPrim()).Bind(self.usdMaterials[materialIdx])

            gltfMaterial = self.gltf['materials'][materialIdx]
            if 'doubleSided' in gltfMaterial and gltfMaterial['doubleSided'] == True:
                doubleSidedAttr = usdMesh.CreateDoubleSidedAttr()
                doubleSidedAttr.Set(True)

        return usdMesh


    #TODO: Support instansing
    def processMesh(self, nodeIdx, path, underSkeleton):
        gltfNode = self.gltf['nodes'][nodeIdx]
        meshIdx = gltfNode['mesh']
        gltfMesh = self.gltf['meshes'][meshIdx]

        skinIdx = gltfNode['skin'] if 'skin' in gltfNode else -1

        gltfPrimitives = gltfMesh['primitives']

        if len(gltfPrimitives) == 1:
            usdGeom = self.processPrimitive(nodeIdx, gltfPrimitives[0], path, skinIdx, underSkeleton)
        else:
            usdGeom = UsdGeom.Xform.Define(self.usdStage, path)
            for i in range(len(gltfPrimitives)):
                newPrimitivePath = path + '/primitive_' + str(i)
                self.processPrimitive(nodeIdx, gltfPrimitives[i], newPrimitivePath, skinIdx, underSkeleton)

        return usdGeom


    def processNode(self, nodeIdx, path, underSkeleton, indent):
        gltfNode = self.gltf['nodes'][nodeIdx]

        skeletonByJoint = self.skinning.findSkeletonByJoint(str(nodeIdx))

        name = getName(gltfNode, 'node_', nodeIdx)
        if name in self.nodeNames:
            name = name + '_' + str(nodeIdx)
        self.nodeNames[name] = name

        if skeletonByJoint is not None and skeletonByJoint.sdfPath:
            # collapse object hierarchy inside skeleton
            newPath = skeletonByJoint.sdfPath + '/' + name
        else:
            newPath = path + '/' + name

        usdGeom = None
        skeleton = self.skinning.findSkeletonByRoot(str(nodeIdx))
        if skeleton is not None:
            if self.verbose:
                print(indent + 'SkelRoot:', name)
            usdGeom = skeleton.makeUsdSkeleton(self.usdStage, newPath, self.nodeManager)
            underSkeleton = skeleton
        elif skeletonByJoint is not None and 'mesh' not in gltfNode:
            pass
        else:
            if 'mesh' in gltfNode:
                if 'skin' in gltfNode or underSkeleton is not None:
                    self.skeletonByNode[str(nodeIdx)] = underSkeleton
                    if self.verbose:
                        print(indent + 'Skinned mesh:', name)
                elif self.meshHasMorphTargets(gltfNode['mesh']):
                    # Morph-only mesh: UsdSkel blendshapes only evaluate under a
                    # SkelRoot with a bound Skeleton, so synthesize a jointless
                    # one (same structure Blender's USD exporter produces).
                    if self.verbose:
                        print(indent + 'Morph mesh (synthesized SkelRoot):', name)
                    usdGeom = UsdSkel.Root.Define(self.usdStage, newPath)
                    skelPath = newPath + '/Skel'
                    UsdSkel.Skeleton.Define(self.usdStage, skelPath)
                    self._currentMorphSkelPath = skelPath
                    self.processMesh(nodeIdx, newPath + '/' + name + '_geo', underSkeleton)
                    self._currentMorphSkelPath = None
                else:
                    if self.verbose:
                        print(indent + 'Mesh:', name)
                    usdGeom = self.processMesh(nodeIdx, newPath, underSkeleton)
            else:
                if self.verbose:
                    print(indent + 'Node:', name)
                usdGeom = UsdGeom.Xform.Define(self.usdStage, newPath)

            if usdGeom is not None:
                if 'matrix' in gltfNode:
                    usdGeom.AddTransformOp().Set(getMatrix(gltfNode['matrix']))
                else:
                    if 'translation' in gltfNode:
                        usdGeom.AddTranslateOp().Set(getVec3(gltfNode['translation']))
                    if 'rotation' in gltfNode:
                        if self.legacyModifier is None:
                            usdGeom.AddOrientOp().Set(getQuat(gltfNode['rotation']))
                        else:
                            usdGeom.AddRotateXYZOp().Set(self.legacyModifier.eulerWithQuat(getQuat(gltfNode['rotation'])))
                    if 'scale' in gltfNode:
                        usdGeom.AddScaleOp().Set(getVec3(gltfNode['scale']))

        if usdGeom is not None:
            self.usdGeoms[nodeIdx] = usdGeom

        # process child nodes recursively
        if underSkeleton is not None:
            newPath = path # keep meshes directly under SkelRoot scope

        if 'children' in gltfNode:
            self.processNodeChildren(gltfNode['children'], newPath, underSkeleton, indent + '  ')


    def processNodeChildren(self, gltfChildren, path, underSkeleton, indent='  '):
        for nodeIdx in gltfChildren:
            self.processNode(nodeIdx, path, underSkeleton, indent)


    def processNodeTransformAnimation(self):
        for gltfAnim in self.gltf['animations'] if 'animations' in self.gltf else []:
            for gltfChannel in gltfAnim['channels']:
                gltfTarget = gltfChannel['target']
                if 'node' not in gltfTarget:
                    continue
                nodeIdx = gltfTarget['node']

                skeleton = self.skinning.findSkeletonByJoint(str(nodeIdx))
                if skeleton is not None:
                    continue

                targetPath = gltfTarget['path']

                samplerIdx = gltfChannel['sampler']
                gltfSampler = gltfAnim['samplers'][samplerIdx]
                interpolation = gltfSampler['interpolation'] if 'interpolation' in gltfSampler else 'LINEAR'
                keyTimesAcc = Accessor(self, gltfSampler['input'])
                keyValuesAcc = Accessor(self, gltfSampler['output'])
                data = keyValuesAcc.data

                if nodeIdx not in self.usdGeoms:
                    continue

                usdGeom = self.usdGeoms[nodeIdx]

                xformOp = None
                getValueFromData = getGfQuatfFromData if targetPath == 'rotation' else getGfVec3fFromData

                if self.legacyModifier is not None and targetPath == 'rotation':
                    getValueFromData = self.legacyModifier.getEulerFromData

                if targetPath == 'translation':
                    xformOp = getXformOp(usdGeom, UsdGeom.XformOp.TypeTranslate)
                    if xformOp == None:
                        xformOp = usdGeom.AddTranslateOp()
                elif targetPath == 'rotation':
                    if self.legacyModifier is None:
                        xformOp = getXformOp(usdGeom, UsdGeom.XformOp.TypeOrient)
                        if xformOp == None:
                            xformOp = usdGeom.AddOrientOp()
                    else:
                        xformOp = getXformOp(usdGeom, UsdGeom.XformOp.TypeRotateXYZ)
                        if xformOp == None:
                            xformOp = usdGeom.AddRotateXYZOp()
                elif targetPath == 'scale':
                    xformOp = getXformOp(usdGeom, UsdGeom.XformOp.TypeScale)
                    if xformOp == None:
                        xformOp = usdGeom.AddScaleOp()

                if xformOp == None:
                    continue

                values = self.getInterpolatedValues(interpolation, keyTimesAcc, keyValuesAcc, getValueFromData)
                for time, value in values.items():
                    xformOp.Set(time = time, value = value)


    def processSkinnedMeshes(self):
        for strNodeIdx, skeleton in self.skeletonByNode.items():
            nodeIdx = int(strNodeIdx)
            gltfNode = self.gltf['nodes'][nodeIdx]
            if skeleton is None and 'skin' in gltfNode:
                skinIdx = gltfNode['skin']
                skin = self.skinning.skins[skinIdx]
                skeleton = skin.skeleton

            name = getName(gltfNode, 'node_', nodeIdx)
            if name in self.nodeNames:
                name = name + '_' + str(nodeIdx)
            self.nodeNames[name] = name

            newPath = skeleton.sdfPath + '/' + name
            usdGeom = self.processMesh(nodeIdx, newPath, skeleton)
            if usdGeom is not None:
                self.usdGeoms[nodeIdx] = usdGeom


    def meshHasMorphTargets(self, meshIdx):
        for primitive in self.gltf['meshes'][meshIdx].get('primitives', []):
            if primitive.get('targets'):
                return True
        return False

    def _warnMorphTargets(self):
        # Morph targets ARE authored (UsdSkel.BlendShape + blendShapeWeights),
        # exceeding Apple's original usdzconvert 0.62 and Google's usd_from_gltf
        # (neither implements them). Two caveats still warrant a warning:
        # sparse target accessors are dropped, and AR Quick Look's blendshape
        # PLAYBACK is historically unreliable — data-valid != plays-on-device.
        hasMorphTargets = any(
            primitive.get('targets')
            for mesh in self.gltf.get('meshes', [])
            for primitive in mesh.get('primitives', []))
        if hasMorphTargets:
            # Playback verified on-device in AR Quick Look (2026-07-08, see
            # docs/on-device-checklist.md) — informational, not a warning.
            print('morph targets detected: authored as USD blend shapes.')

    def makeUsdStage(self):
        if self._loadFailed:
            return None
        # Draco-compressed geometry lives inside the extension, not in plain
        # accessors — the parser cannot read it. Fail with guidance instead of
        # a KeyError deep in Accessor.
        extensions = (self.gltf.get('extensionsRequired', [])
                      + self.gltf.get('extensionsUsed', []))
        if 'KHR_draco_mesh_compression' in extensions:
            usdUtils.printError(
                'this file uses Draco mesh compression '
                '(KHR_draco_mesh_compression), which is not supported. '
                'Re-export without Draco, or decompress it first, e.g.: '
                'npx @gltf-transform/cli copy input.glb output.glb')
            return None
        self._warnMorphTargets()
        self.usdStage = self.asset.makeUsdStage()
        #gltf units for all linear distance are meters
        if self.legacyModifier is None:
            self.usdStage.SetMetadata("metersPerUnit", 1)
        self.createMaterials()
        self.prepareSkinning()
        self.prepareAnimations()
        self.processNodeChildren(self.gltf['scenes'][0]['nodes'], self.asset.getGeomPath(), None)
        self.processSkeletonAnimation()
        self.processSkinnedMeshes()
        self.processNodeTransformAnimation()
        self.processMorphWeightAnimations()
        self.asset.finalize()
        return self.usdStage



def usdStageWithGlTF(gltfPath, usdPath, legacyModifier, copyTextures, verbose):
    converter = glTFConverter(gltfPath, usdPath, legacyModifier, copyTextures, verbose)
    return converter.makeUsdStage()

